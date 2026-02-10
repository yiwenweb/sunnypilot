#pragma once

#include "opendbc/safety/safety_declarations.h"

// Safety-relevant CAN messages for BYD vehicles (Tang DM 2018 and similar)
// Based on byd_tang_dm_2018.dbc

// RX messages (from vehicle ECUs on Bus 0)
#define BYD_EPS              0x11FU  // 287 - Steering angle and rate from EPS
#define BYD_CARSPEED         0x121U  // 289 - Vehicle speed display
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
      acc_main_on = GET_BIT(msg, 8U);
      mads_button_press = acc_main_on ? MADS_BUTTON_PRESSED : MADS_BUTTON_NOT_PRESSED;
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
  // Default forwarding (Bus 0 <-> Bus 2) is handled by get_fwd_bus() in safety.h.
  // All TX messages use check_relay=false, so static blocking does NOT apply.
  // We handle ALL forwarding control here dynamically.
  //
  // BYD CAN 架构:
  //   原厂 MPC 在 Bus 2 上发送 790/813/814/815，panda 转发到 Bus 0 给 EPS/ESP。
  //   openpilot 也在 Bus 0 上发送 790/813/814/815。
  //   当 openpilot 控制时，必须阻止 Bus 2→Bus 0 方向的原厂 MPC 消息，
  //   否则 EPS/ESP 收到两套冲突的消息 → AEB/安全系统报错。
  //   当 openpilot 不控制时，让原厂 MPC 消息正常通过。

  if (bus_num == 0) {
    // Bus 0 → Bus 2 方向:
    // 阻止 openpilot 发送的消息回传到 Bus 2（避免原厂 MPC 收到冲突消息）
    // 条件: 横向或纵向激活，或者非 stock longitudinal 模式
    if (is_lat_active() || !byd_stock_longitudinal) {
      if ((addr == BYD_ACC_MPC_STATE) || (addr == BYD_ACC_HUD_ADAS) ||
          (addr == BYD_ACC_CMD) || (addr == BYD_ACC_AEB)) {
        return true;
      }
    }
  }

  if (bus_num == 2) {
    // Bus 2 → Bus 0 方向:
    // 当 openpilot 正在控制时，阻止原厂 MPC 对应消息到达 EPS/ESP
    // 当 openpilot 未控制时，放行原厂 MPC 消息（保持原厂功能正常）
    //
    // 关键修复: 分别处理横向和纵向消息
    //
    // 790 (ACC_MPC_STATE) — 转向控制消息:
    //   使用 is_lat_active() 判断。MADS 模式下按 ACC 开关只激活横向控制
    //   (controls_allowed_lat=true)，不会设置 controls_allowed=true。
    //   如果只检查 controls_allowed，横向激活时原厂 MPC 的 790 仍会转发到 Bus 0，
    //   与 openpilot 发送的 790 冲突 → CAN 总线仲裁错误 → canValid=false
    //   → locationd inputsOK=false → "communication issue" → "locationd temporary error"
    //
    // 813/814/815 — 纵向控制消息 (ACC HUD/CMD/AEB):
    //   使用 controls_allowed 判断。只有按 RES/SET engage 后才发送替代消息。
    //   横向-only 模式下，openpilot 不发送 813/814/815，
    //   所以必须让原厂 MPC 的 813/814/815 继续通过，否则 ACC/AEB 系统会报错。
    // 横向激活时: 阻止所有 ACC 消息 (790/813/814/815)
    // openpilot 在 latActive 时发送全套 ACC 消息（814/815 用空闲值），
    // 必须阻止原厂 MPC 的对应消息，否则 EPS/ESP 收到两套冲突消息。
    if (is_lat_active()) {
      if ((addr == BYD_ACC_MPC_STATE) || (addr == BYD_ACC_HUD_ADAS) ||
          (addr == BYD_ACC_CMD) || (addr == BYD_ACC_AEB)) {
        return true;
      }
    }
    // 纵向激活时: 同样阻止（is_lat_active 可能不包含纵向-only 场景）
    if (controls_allowed) {
      if ((addr == BYD_ACC_CMD) || (addr == BYD_ACC_AEB)) {
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
    // EPS (287) - 5 bytes, 20Hz, no counter/checksum in DBC
    {.msg = {{BYD_EPS, 0, 5, 20U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // CARSPEED (289) - 8 bytes, 20Hz, no counter/checksum in DBC
    {.msg = {{BYD_CARSPEED, 0, 8, 20U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // DRIVE_STATE (578) - 8 bytes, 20Hz, has counter+checksum but algorithm unverified
    {.msg = {{BYD_DRIVE_STATE, 0, 8, 20U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // ACC_EPS_STATE (792) - 8 bytes, 20Hz, NO counter/checksum signals in DBC
    {.msg = {{BYD_ACC_EPS_STATE, 0, 8, 20U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // PEDAL (834) - 8 bytes, 20Hz, has checksum but no counter, algorithm unverified
    {.msg = {{BYD_PEDAL, 0, 8, 20U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // PCM_BUTTONS (944) - 8 bytes, 20Hz, NO counter/checksum signals in DBC
    {.msg = {{BYD_PCM_BUTTONS, 0, 8, 20U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
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
