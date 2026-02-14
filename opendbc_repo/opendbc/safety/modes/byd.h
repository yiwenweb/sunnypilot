#pragma once

#include "opendbc/safety/safety_declarations.h"

// Safety-relevant CAN messages for BYD vehicles (Tang DM 2018 and similar)
// Based on byd_tang_dm_2018.dbc

// RX messages (from vehicle ECUs on Bus 0)
#define BYD_EPS              0x11FU  // 287 - Steering angle and rate from EPS
#define BYD_CARSPEED         0x121U  // 289 - Vehicle speed display
#define BYD_YAW_RATE         0x222U  // 546 - Yaw rate from ESP
#define BYD_AXAY             0x223U  // 547 - Longitudinal acceleration from ESP
#define BYD_DRIVE_STATE      0x242U  // 578 - Gear, brake pedal from VCU
#define BYD_ACC_EPS_STATE    0x318U  // 792 - EPS feedback, driver torque
#define BYD_PEDAL            0x342U  // 834 - Accelerator and brake pedal
#define BYD_PCM_BUTTONS      0x3B0U  // 944 - Cruise control buttons

// TX messages (from openpilot)
#define BYD_ACC_MPC_STATE    0x316U  // 790 - LKAS control output (Bus 0)
#define BYD_ACC_HUD_ADAS     0x32DU  // 813 - ACC HUD display (Bus 0)
#define BYD_ACC_CMD          0x32EU  // 814 - ACC acceleration command (Bus 0)
#define BYD_ACC_AEB          0x32FU  // 815 - AEB control (Bus 0)
#define BYD_PCM_BUTTONS_FWD  0x3B0U  // 944 - Button forwarding (Bus 2)

// CAN bus numbers
#define BYD_MAIN_BUS 0U
#define BYD_CAM_BUS  2U

// BYD safety param flags
#define BYD_PARAM_STOCK_LONGITUDINAL (1U << 0)

// Counter extraction
// EPS (287): 5-byte message, no counter in DBC signal definitions
// Most other messages: no reliable counter confirmed on real vehicle
// For safety, we ignore counters on all messages until validated
static uint8_t byd_get_counter(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

// Checksum: algorithm is UNVERIFIED per DBC documentation
// DBC comments say "sum(bytes[0:7]) & 0xFF" but bydcan.py uses nibble-based algorithm
// Until validated on real vehicle, ignore checksums on all RX messages
static uint32_t byd_get_checksum(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

static uint32_t byd_compute_checksum(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

// LKAS steering limits for BYD
// LKAS_Output is 11-bit signed, range [-1024, 1023]
static const TorqueSteeringLimits BYD_STEERING_LIMITS = {
  .max_torque = 1023,             // 11-bit signed max (matches STEER_MAX in values.py)
  .max_rate_up = 10,              // torque increase per cycle
  .max_rate_down = 25,            // torque decrease per cycle
  .max_rt_delta = 375,            // 10 rate_up * 100Hz * 250ms = 250, * 1.5 safety = 375
  .type = TorqueDriverLimited,

  .driver_torque_allowance = 80,
  .driver_torque_multiplier = 3,

  .max_torque_error = 350,

  .min_valid_request_frames = 10,
  .max_invalid_request_frames = 5,
  .min_valid_request_rt_interval = 250000U,
  .has_steer_req_tolerance = true,
};

static bool byd_stock_longitudinal = false;

static void byd_rx_hook(const CANPacket_t *msg) {
  if (msg->bus == BYD_MAIN_BUS) {
    // Update vehicle speed from CARSPEED (289)
    // Signal: CarDisplaySpeed - 12-bit unsigned, scale 0.0735 km/h (per DBC)
    if (msg->addr == BYD_CARSPEED) {
      int speed_raw = (msg->data[0] | ((msg->data[1] & 0x0FU) << 8));
      // scale 0.0735 km/h -> multiply by 0.0735 then convert to m/s
      // 0.0735 * KPH_TO_MS = 0.0735 / 3.6 ≈ 0.020417
      // Use integer math: speed_raw * 20417 / 1000000 gives m/s * VEHICLE_SPEED_FACTOR
      UPDATE_VEHICLE_SPEED((float)speed_raw * 0.0735f * KPH_TO_MS);
    }

    // Update steering angle from EPS (287)
    // Signal: SteeringAngle - 16-bit signed, scale 0.1 deg
    if (msg->addr == BYD_EPS) {
      int angle_raw = (msg->data[0] | (msg->data[1] << 8));
      if (angle_raw > 32767) {
        angle_raw -= 65536;  // convert to signed
      }
      update_sample(&angle_meas, angle_raw);  // in 0.1 deg units
    }

    // Update driver torque from ACC_EPS_STATE (792)
    // Signal: SteerDriverTorque - 12-bit signed at bits 24-35
    if (msg->addr == BYD_ACC_EPS_STATE) {
      int torque_driver_raw = ((msg->data[3] | (msg->data[4] << 8)) & 0xFFFU);
      if (torque_driver_raw > 2047) {
        torque_driver_raw -= 4096;  // convert to signed
      }
      update_sample(&torque_driver, torque_driver_raw);
    }

    // Update brake pedal from DRIVE_STATE (578)
    // Signal: BrakePressed - 1 bit at bit 37
    if (msg->addr == BYD_DRIVE_STATE) {
      brake_pressed = GET_BIT(msg, 37U);
    }

    // Update gas pedal from PEDAL (834)
    // Signal: AcceleratorPedal - 8-bit, scale 0.01
    if (msg->addr == BYD_PEDAL) {
      gas_pressed = msg->data[0] > 0U;
    }

    // Update vehicle moving state from DRIVE_STATE (578)
    // Signal: Gear - 3 bits at bits 40-42
    // 1=P, 2=R, 3=N, 4=D
    if (msg->addr == BYD_DRIVE_STATE) {
      unsigned int gear = (msg->data[5] & 0x7U);
      vehicle_moving = (gear != 1U);  // moving if not in Park
    }

    // Update acc_main_on from PCM_BUTTONS (944)
    // BTN_TOGGLE_ACC_OnOff at bit 8 — this is a state signal (1=ACC on, 0=ACC off)
    // With pcmCruise=False, openpilot manages controls_allowed via heartbeat.
    // acc_main_on is used by MADS for lateral-only activation.
    if (msg->addr == BYD_PCM_BUTTONS) {
      bool prev_acc = acc_main_on;
      acc_main_on = GET_BIT(msg, 8U);
      mads_button_press = acc_main_on ? MADS_BUTTON_PRESSED : MADS_BUTTON_NOT_PRESSED;

      // 直接控制 controls_allowed_lat — 绕过 MADS 状态机
      // MADS 状态机通过 mads_state_update → m_update_control_state 来设置
      // controls_allowed_lat，但在实际测试中始终无法正常工作。
      // 可能原因: mads_state_update 在 578(50Hz) 上调用，而 944(20Hz) 频率更低，
      // 导致 edge detection 时序问题，或者 m_mads_state_init 被反复调用重置状态。
      // 直接方案: ACC ON → controls_allowed_lat=true, ACC OFF → false
      if (acc_main_on && !prev_acc) {
        // ACC OFF→ON: 激活横向控制
        m_mads_state.controls_allowed_lat = true;
        m_mads_state.system_enabled = true;
      } else if (!acc_main_on && prev_acc) {
        // ACC ON→OFF: 关闭横向控制
        m_mads_state.controls_allowed_lat = false;
      }
    }

    // 关键修复: 手动调用 mads_state_update
    // BYD 所有 TX 消息都设置了 check_relay=false（因为原厂 MPC 在 Bus 2 上发送
    // 790/813/814/815，如果 check_relay=true 会触发 relay_malfunction）。
    // 但 safety.h 中的 mads_state_update 只在 stock_ecu_check() 中被调用，
    // 而 stock_ecu_check() 只在 check_relay=true 的消息匹配时才执行。
    // 因此 mads_state_update 永远不会被调用 → controls_allowed_lat 永远为 false
    // → is_lat_active() 永远为 false → 所有 790 消息被 panda 拒绝。
    //
    // 修复: 在收到 DRIVE_STATE (578, 20Hz) 时手动调用 mads_state_update，
    // 确保 MADS 状态机正常运行。
    if (msg->addr == BYD_DRIVE_STATE) {
      // 额外修复: mads_set_alternative_experience() 调用 m_mads_state_init()
      // 重置 system_enabled=false。C++ pandad 可能在 set_safety_mode 之后
      // 调用 set_alternative_experience，导致 system_enabled 被重置。
      // 直接恢复 system_enabled 而不重置其他 MADS 状态。
      if ((alternative_experience & ALT_EXP_ENABLE_MADS) && !m_mads_state.system_enabled) {
        m_mads_state.system_enabled = true;
      }
      mads_state_update(vehicle_moving, acc_main_on, controls_allowed,
                        brake_pressed || regen_braking, steering_disengage);
    }
  }
}

static bool byd_tx_hook(const CANPacket_t *msg) {
  bool tx = true;

  // Safety check for ACC_MPC_STATE (790) - LKAS control on Bus 0
  if ((msg->addr == BYD_ACC_MPC_STATE) && (msg->bus == BYD_MAIN_BUS)) {
    // Signal: LKAS_Output - 11-bit signed at bits 16-26
    int lkas_output = ((msg->data[2] | (msg->data[3] << 8)) & 0x7FFU);
    if (lkas_output > 1023) {
      lkas_output -= 2048;  // convert to signed
    }

    // Signal: LKAS_Active - 1 bit at bit 28
    bool steer_req = GET_BIT(msg, 28U);

    // Check torque limits
    if (steer_torque_cmd_checks(lkas_output, steer_req, BYD_STEERING_LIMITS)) {
      tx = false;
    }
  }

  // Safety check for ACC_CMD (814) - Longitudinal control on Bus 0
  if ((msg->addr == BYD_ACC_CMD) && (msg->bus == BYD_MAIN_BUS)) {
    // When using stock longitudinal, block all ACC_CMD messages from openpilot
    if (byd_stock_longitudinal) {
      tx = false;
    } else {
      // Signal: AccelCmd - 8-bit unsigned, scale 0.05, offset -5
      // Raw value 100 = 0 m/s^2
      unsigned int accel_raw = msg->data[0];

      // Limits: -3.5 m/s^2 (raw 30) to +2.0 m/s^2 (raw 140)
      bool violation = (accel_raw > 140U) || (accel_raw < 30U);

      if (get_longitudinal_allowed()) {
        // 纵向控制激活: 允许完整加速度范围
      } else if (is_lat_active()) {
        // 横向-only 模式: 只允许 accel=0 (raw=100) 的空闲消息
        // EPS 需要看到完整的 ACC 消息组才会回复 LKAS_Prepared=1
        violation |= (accel_raw != 100U);
      } else {
        // 既没有横向也没有纵向: 不允许发送
        violation = true;
      }

      if (violation) {
        tx = false;
      }
    }
  }

  // Safety check for ACC_HUD_ADAS (813) on Bus 0
  if ((msg->addr == BYD_ACC_HUD_ADAS) && (msg->bus == BYD_MAIN_BUS)) {
    // When using stock longitudinal, block HUD messages from openpilot
    if (byd_stock_longitudinal) {
      tx = false;
    }
  }

  // Safety check for ACC_AEB (815) on Bus 0
  if ((msg->addr == BYD_ACC_AEB) && (msg->bus == BYD_MAIN_BUS)) {
    // When using stock longitudinal, block AEB messages from openpilot
    if (byd_stock_longitudinal) {
      tx = false;
    }
  }

  return tx;
}

static bool byd_fwd_hook(int bus_num, int addr) {
  // BYD CAN 架构 (panda 中间人):
  //   Bus 0 = 车辆主总线 (EPS, ESP, VCU 等所有 ECU)
  //   Bus 2 = 原厂 MPC (前摄像头)
  //   panda 默认双向转发 Bus 0 <-> Bus 2 (get_fwd_bus)
  //
  // 需要拦截的三类信号:
  //   1. ACC 控制指令: 813 (HUD), 814 (AccelCmd), 815 (AEB)
  //   2. LKA/车道保持指令: 790 (LKAS_Output)
  //   3. EPS 反馈: 792 (EPS→MPC 方向)
  //
  // === Bus 2 → Bus 0 (原厂 MPC → ECU) ===
  // 横向激活时: 拦截 790/813/814/815，openpilot 在 Bus 0 上发送替代消息
  // 未激活时: 全部透传，保持原厂 MPC 正常控制
  //
  // === Bus 0 → Bus 2 (ECU/openpilot → MPC) ===
  // 横向激活时:
  //   拦截 790/813/814/815: openpilot 发到 Bus 0 的消息不能回传到 Bus 2，
  //     否则 MPC 收到与自己发出内容不同的同 ID 消息会报错
  //   拦截 792: openpilot 发假 792 到 Bus 2，真实 792 不能同时到达 MPC
  // 未激活时: 全部透传

  bool dominated = is_lat_active();

  if (bus_num == 2) {
    // Bus 2 → Bus 0: 拦截原厂 MPC 的控制消息
    if (dominated) {
      if ((addr == BYD_ACC_MPC_STATE) ||   // 790 - LKA 转向
          (addr == BYD_ACC_HUD_ADAS) ||    // 813 - ACC HUD
          (addr == BYD_ACC_CMD) ||          // 814 - ACC 加速度
          (addr == BYD_ACC_AEB)) {          // 815 - AEB
        return true;
      }
    }
  }

  if (bus_num == 0) {
    // Bus 0 → Bus 2: 拦截 openpilot 消息回传 + 真实 EPS 反馈
    // 790/813/814/815 在原厂 Bus 0 上不存在（只有 MPC 在 Bus 2 上发送），
    // 所以 Bus 0 上出现的这些消息一定是 openpilot 发的，始终拦截不影响原厂功能。
    // 792 只在横向激活时拦截（未激活时 MPC 需要收到真实 EPS 反馈）。
    if ((addr == BYD_ACC_MPC_STATE) ||   // 790 - openpilot 发的，不回传给 MPC
        (addr == BYD_ACC_HUD_ADAS) ||    // 813
        (addr == BYD_ACC_CMD) ||          // 814
        (addr == BYD_ACC_AEB)) {          // 815
      return true;
    }
    if (dominated) {
      if (addr == BYD_ACC_EPS_STATE) {    // 792 - 真实 EPS 反馈，用假的替代
        return true;
      }
    }
  }

  return false;
}


static safety_config byd_init(uint16_t param) {
  byd_stock_longitudinal = GET_FLAG(param, BYD_PARAM_STOCK_LONGITUDINAL);

  // RX checks: messages we monitor from vehicle ECUs on Bus 0
  // All checksums and counters are UNVERIFIED, so ignore them all.
  // This is safe because we still validate message presence (timeout check).
  static RxCheck byd_rx_checks[] = {
    // 实车嗅探数据 (sniff_all_buses.py, 22.9秒采样):
    //   EPS: 100Hz, CARSPEED/DRIVE_STATE/PEDAL/ACC_EPS_STATE/YAW_RATE/AXAY: 50Hz
    //   PCM_BUTTONS/BELT: 20Hz, BCM/STALKS: ~1.5-2Hz, EPB: 1Hz
    //   BCM/STALKS/EPB 频率太低，不加入 RxCheck（非安全关键信号）
    //
    // 频率设为实际值的 50%，safety_tick 超时 = MAX(10/freq, 1s)
    // EPS (287) - 5 bytes, 实际 100Hz
    {.msg = {{BYD_EPS, 0, 5, 50U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // CARSPEED (289) - 8 bytes, 实际 50Hz
    {.msg = {{BYD_CARSPEED, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // YAW_RATE (546) - 8 bytes, 实际 50Hz
    {.msg = {{BYD_YAW_RATE, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // AXAY (547) - 8 bytes, 实际 50Hz
    {.msg = {{BYD_AXAY, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // DRIVE_STATE (578) - 8 bytes, 实际 50Hz
    {.msg = {{BYD_DRIVE_STATE, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // ACC_EPS_STATE (792) - 8 bytes, 实际 50Hz（但可能在某些状态下不发送，设低频）
    {.msg = {{BYD_ACC_EPS_STATE, 0, 8, 1U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // PEDAL (834) - 8 bytes, 实际 50Hz
    {.msg = {{BYD_PEDAL, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // PCM_BUTTONS (944) - 8 bytes, 实际 20Hz
    {.msg = {{BYD_PCM_BUTTONS, 0, 8, 10U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
  };

  // TX whitelist: messages openpilot is allowed to send
  // check_relay=false for all: BYD 的原厂 MPC 在 Bus 2 上发送 790/813/814/815，
  // panda 默认转发到 Bus 0。如果 check_relay=true，static blocking 会始终阻止
  // Bus 2→Bus 0 方向的转发，导致 EPS/ESP 收不到原厂 MPC 消息 → 车辆报 AEB 错误。
  // 改为 check_relay=false，由 byd_fwd_hook 根据 controls_allowed 动态控制转发。
  static const CanMsg BYD_TX_MSGS[] = {
    {BYD_ACC_MPC_STATE, BYD_MAIN_BUS, 8, .check_relay = false},  // 790 - LKAS control
    {BYD_ACC_HUD_ADAS,  BYD_MAIN_BUS, 8, .check_relay = false},  // 813 - ACC HUD
    {BYD_ACC_CMD,        BYD_MAIN_BUS, 8, .check_relay = false},  // 814 - ACC command
    {BYD_ACC_AEB,        BYD_MAIN_BUS, 8, .check_relay = false},  // 815 - AEB
    {BYD_ACC_EPS_STATE,  BYD_CAM_BUS,  8, .check_relay = false},  // 792 - Fake EPS feedback to MPC
    {BYD_PCM_BUTTONS_FWD, BYD_CAM_BUS, 8, .check_relay = false},  // 944 - Button forward to Bus 2
  };

  return BUILD_SAFETY_CFG(byd_rx_checks, BYD_TX_MSGS);
}

const safety_hooks byd_hooks = {
  .init = byd_init,
  .rx = byd_rx_hook,
  .tx = byd_tx_hook,
  .fwd = byd_fwd_hook,
  .get_counter = byd_get_counter,
  .get_checksum = byd_get_checksum,
  .compute_checksum = byd_compute_checksum,
};
