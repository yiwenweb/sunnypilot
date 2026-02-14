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

// Counter extraction — disabled (unverified on real vehicle)
static uint8_t byd_get_counter(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

// Checksum: verified via real vehicle sniff data
// Algorithm: CHECKSUM = (0xFF - sum(bytes[0:7])) & 0xFF
// Disabled in safety layer (RX validation not needed)
static uint32_t byd_get_checksum(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

static uint32_t byd_compute_checksum(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

// LKAS steering limits for BYD
static const TorqueSteeringLimits BYD_STEERING_LIMITS = {
  .max_torque = 1023,
  .max_rate_up = 10,
  .max_rate_down = 25,
  .max_rt_delta = 375,
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
    if (msg->addr == BYD_CARSPEED) {
      int speed_raw = (msg->data[0] | ((msg->data[1] & 0x0FU) << 8));
      UPDATE_VEHICLE_SPEED((float)speed_raw * 0.0735f * KPH_TO_MS);
    }

    // Update steering angle from EPS (287)
    if (msg->addr == BYD_EPS) {
      int angle_raw = (msg->data[0] | (msg->data[1] << 8));
      if (angle_raw > 32767) {
        angle_raw -= 65536;
      }
      update_sample(&angle_meas, angle_raw);
    }

    // Update driver torque from ACC_EPS_STATE (792)
    if (msg->addr == BYD_ACC_EPS_STATE) {
      int torque_driver_raw = ((msg->data[3] | (msg->data[4] << 8)) & 0xFFFU);
      if (torque_driver_raw > 2047) {
        torque_driver_raw -= 4096;
      }
      update_sample(&torque_driver, torque_driver_raw);
    }

    // Update brake pedal from DRIVE_STATE (578)
    if (msg->addr == BYD_DRIVE_STATE) {
      brake_pressed = GET_BIT(msg, 37U);
    }

    // Update gas pedal from PEDAL (834)
    if (msg->addr == BYD_PEDAL) {
      gas_pressed = msg->data[0] > 0U;
    }

    // Update vehicle moving state from DRIVE_STATE (578)
    if (msg->addr == BYD_DRIVE_STATE) {
      unsigned int gear = (msg->data[5] & 0x7U);
      vehicle_moving = (gear != 1U);
    }

    // Update acc_main_on from PCM_BUTTONS (944)
    if (msg->addr == BYD_PCM_BUTTONS) {
      acc_main_on = GET_BIT(msg, 8U);
      mads_button_press = acc_main_on ? MADS_BUTTON_PRESSED : MADS_BUTTON_NOT_PRESSED;
    }

    // 手动调用 mads_state_update (see previous comments for explanation)
    if (msg->addr == BYD_DRIVE_STATE) {
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
    int lkas_output = ((msg->data[2] | (msg->data[3] << 8)) & 0x7FFU);
    if (lkas_output > 1023) {
      lkas_output -= 2048;
    }
    bool steer_req = GET_BIT(msg, 28U);

    if (steer_torque_cmd_checks(lkas_output, steer_req, BYD_STEERING_LIMITS)) {
      tx = false;
    }
  }

  // Safety check for ACC_CMD (814) - Longitudinal control on Bus 0
  // 关键改动: 始终允许空闲帧 (AccelCmd=0, raw=100)
  // openpilot 始终发送 814，未激活时发送空闲值
  if ((msg->addr == BYD_ACC_CMD) && (msg->bus == BYD_MAIN_BUS)) {
    if (byd_stock_longitudinal) {
      tx = false;
    } else {
      unsigned int accel_raw = msg->data[0];

      if (get_longitudinal_allowed()) {
        // 纵向控制激活: 允许完整加速度范围 (raw 30-140)
        bool violation = (accel_raw > 140U) || (accel_raw < 30U);
        if (violation) {
          tx = false;
        }
      } else {
        // 未激活: 只允许 accel=0 (raw=100) 的空闲帧
        if (accel_raw != 100U) {
          tx = false;
        }
      }
    }
  }

  // Safety check for ACC_HUD_ADAS (813) on Bus 0
  if ((msg->addr == BYD_ACC_HUD_ADAS) && (msg->bus == BYD_MAIN_BUS)) {
    if (byd_stock_longitudinal) {
      tx = false;
    }
  }

  // Safety check for ACC_AEB (815) on Bus 0
  if ((msg->addr == BYD_ACC_AEB) && (msg->bus == BYD_MAIN_BUS)) {
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
  //
  // 关键设计: openpilot 始终发送 790/813/814/815 替代帧
  // 因此 fwd_hook 始终拦截 MPC 的这些帧，不存在切换间隙
  // 这避免了:
  //   1. 切换瞬间 ECU 同时收到 MPC 和 openpilot 的帧
  //   2. 切换瞬间帧丢失（MPC 被拦截但 openpilot 还没发）
  //   3. counter 跳变（openpilot counter 从 0 开始 vs MPC counter 在某个值）

  if (bus_num == 2) {
    // Bus 2 → Bus 0: 始终拦截 MPC 的控制帧
    if ((addr == BYD_ACC_MPC_STATE) ||   // 790
        (addr == BYD_ACC_HUD_ADAS) ||    // 813
        (addr == BYD_ACC_CMD) ||          // 814
        (addr == BYD_ACC_AEB)) {          // 815
      return true;
    }
  }

  if (bus_num == 0) {
    // Bus 0 → Bus 2: 拦截 openpilot 发的控制帧（防止回传给 MPC）
    if ((addr == BYD_ACC_MPC_STATE) ||
        (addr == BYD_ACC_HUD_ADAS) ||
        (addr == BYD_ACC_CMD) ||
        (addr == BYD_ACC_AEB)) {
      return true;
    }
    // 792: 始终拦截真实 EPS 的 792，openpilot 始终发送假 792 到 Bus 2
    // 防止 MPC 看到真实 EPS 状态（可能包含 CruiseActivated=1 等）
    if (addr == BYD_ACC_EPS_STATE) {
      return true;
    }
  }

  return false;
}


static safety_config byd_init(uint16_t param) {
  byd_stock_longitudinal = GET_FLAG(param, BYD_PARAM_STOCK_LONGITUDINAL);

  static RxCheck byd_rx_checks[] = {
    {.msg = {{BYD_EPS, 0, 5, 50U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    {.msg = {{BYD_CARSPEED, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    {.msg = {{BYD_YAW_RATE, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    {.msg = {{BYD_AXAY, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    {.msg = {{BYD_DRIVE_STATE, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    {.msg = {{BYD_ACC_EPS_STATE, 0, 8, 1U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    {.msg = {{BYD_PEDAL, 0, 8, 25U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    {.msg = {{BYD_PCM_BUTTONS, 0, 8, 10U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
  };

  static const CanMsg BYD_TX_MSGS[] = {
    {BYD_ACC_MPC_STATE, BYD_MAIN_BUS, 8, .check_relay = false},  // 790
    {BYD_ACC_HUD_ADAS,  BYD_MAIN_BUS, 8, .check_relay = false},  // 813
    {BYD_ACC_CMD,        BYD_MAIN_BUS, 8, .check_relay = false},  // 814
    {BYD_ACC_AEB,        BYD_MAIN_BUS, 8, .check_relay = false},  // 815
    {BYD_ACC_EPS_STATE,  BYD_CAM_BUS,  8, .check_relay = false},  // 792 fake
    {BYD_PCM_BUTTONS_FWD, BYD_CAM_BUS, 8, .check_relay = false},  // 944
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
