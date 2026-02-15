#pragma once

#include "opendbc/safety/safety_declarations.h"

// Safety-relevant CAN messages for BYD vehicles (Tang DM 2018 and similar)

// RX messages (from vehicle ECUs on Bus 0)
#define BYD_EPS              0x11FU  // 287
#define BYD_CARSPEED         0x121U  // 289
#define BYD_YAW_RATE         0x222U  // 546
#define BYD_AXAY             0x223U  // 547
#define BYD_DRIVE_STATE      0x242U  // 578
#define BYD_ACC_EPS_STATE    0x318U  // 792
#define BYD_PEDAL            0x342U  // 834
#define BYD_PCM_BUTTONS      0x3B0U  // 944

// TX messages (from openpilot)
#define BYD_ACC_MPC_STATE    0x316U  // 790
#define BYD_ACC_HUD_ADAS     0x32DU  // 813
#define BYD_ACC_CMD          0x32EU  // 814
#define BYD_ACC_AEB          0x32FU  // 815
#define BYD_PCM_BUTTONS_FWD  0x3B0U  // 944

// CAN bus numbers
#define BYD_MAIN_BUS 0U
#define BYD_CAM_BUS  2U

// BYD safety param flags
#define BYD_PARAM_STOCK_LONGITUDINAL (1U << 0)

static uint8_t byd_get_counter(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

static uint32_t byd_get_checksum(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

static uint32_t byd_compute_checksum(const CANPacket_t *msg) {
  UNUSED(msg);
  return 0U;
}

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

// BYD PCM_BUTTONS button values (BTN_AccUpDown_Cmd)
#define BYD_BTN_NONE    0
#define BYD_BTN_SET     1
#define BYD_BTN_RES     3

static bool byd_stock_longitudinal = false;

// TX-synced 拦截标志: tx_hook 发送 790 成功时设 true, 100ms 超时重置
// fwd_hook 仅在此标志为 true 时拦截 MPC 帧
// 这保证: 非激活时 100% 透传原厂帧, 激活时拦截+替代严格同步
static bool byd_op_tx_active = false;
static uint32_t byd_op_tx_last_ts = 0U;

static void byd_rx_hook(const CANPacket_t *msg) {
  if (msg->bus == BYD_MAIN_BUS) {
    if (msg->addr == BYD_CARSPEED) {
      int speed_raw = (msg->data[0] | ((msg->data[1] & 0x0FU) << 8));
      UPDATE_VEHICLE_SPEED((float)speed_raw * 0.0735f * KPH_TO_MS);
    }

    if (msg->addr == BYD_EPS) {
      int angle_raw = (msg->data[0] | (msg->data[1] << 8));
      if (angle_raw > 32767) {
        angle_raw -= 65536;
      }
      update_sample(&angle_meas, angle_raw);
    }

    if (msg->addr == BYD_ACC_EPS_STATE) {
      int torque_driver_raw = ((msg->data[3] | (msg->data[4] << 8)) & 0xFFFU);
      if (torque_driver_raw > 2047) {
        torque_driver_raw -= 4096;
      }
      update_sample(&torque_driver, torque_driver_raw);
    }

    if (msg->addr == BYD_DRIVE_STATE) {
      brake_pressed = GET_BIT(msg, 37U);
    }

    if (msg->addr == BYD_PEDAL) {
      gas_pressed = msg->data[0] > 0U;
    }

    if (msg->addr == BYD_DRIVE_STATE) {
      unsigned int gear = (msg->data[5] & 0x7U);
      vehicle_moving = (gear != 1U);
    }

    if (msg->addr == BYD_PCM_BUTTONS) {
      acc_main_on = GET_BIT(msg, 8U);
      mads_button_press = acc_main_on ? MADS_BUTTON_PRESSED : MADS_BUTTON_NOT_PRESSED;

      // 简化策略: ACC 开启时始终允许控制
      // selfdrived 通过 buttonEnable 事件管理 engage/disengage 状态
      // panda 只需要在 ACC ON 时允许 TX，不需要精确的按钮落边沿检测
      // cancel 和 ACC OFF 由 selfdrived 处理（buttonCancel 事件）
      if (acc_main_on) {
        controls_allowed = true;
      } else {
        controls_allowed = false;
      }
    }

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

  if ((msg->addr == BYD_ACC_CMD) && (msg->bus == BYD_MAIN_BUS)) {
    if (byd_stock_longitudinal) {
      tx = false;
    } else {
      unsigned int accel_raw = msg->data[0];
      if (get_longitudinal_allowed()) {
        bool violation = (accel_raw > 140U) || (accel_raw < 30U);
        if (violation) { tx = false; }
      } else {
        // 非纵向激活时: 只允许空闲帧 (raw=100, 即 0.0 m/s²)
        // 始终发送空闲帧保持 counter 连续，避免 ECU 因帧消失而报错
        if (accel_raw != 100U) { tx = false; }
      }
    }
  }

  if ((msg->addr == BYD_ACC_HUD_ADAS) && (msg->bus == BYD_MAIN_BUS)) {
    if (byd_stock_longitudinal) { tx = false; }
  }

  if ((msg->addr == BYD_ACC_AEB) && (msg->bus == BYD_MAIN_BUS)) {
    if (byd_stock_longitudinal) { tx = false; }
  }

  // 标记 OP 正在发送: 任何 OP 帧成功发送到 Bus 0 都设置此标志
  // 这确保 fwd_hook 在 OP 开始发送时立即拦截 MPC 帧，避免 Bus 0 上帧冲突
  if (tx && (msg->bus == BYD_MAIN_BUS)) {
    if ((msg->addr == BYD_ACC_MPC_STATE) ||
        (msg->addr == BYD_ACC_HUD_ADAS) ||
        (msg->addr == BYD_ACC_CMD) ||
        (msg->addr == BYD_ACC_AEB)) {
      byd_op_tx_active = true;
      byd_op_tx_last_ts = microsecond_timer_get();
    }
  }

  return tx;
}

static bool byd_fwd_hook(int bus_num, int addr) {
  // 非激活时: 100% 透传, MPC 帧正常到达 ECU
  // 激活时: 拦截 MPC 帧, OP 发替代帧

  // 超时检测: 100ms 没有新 TX → 认为 OP 停止发送 → 恢复透传
  if (byd_op_tx_active) {
    uint32_t now = microsecond_timer_get();
    if ((now - byd_op_tx_last_ts) > 100000U) {
      byd_op_tx_active = false;
    }
  }

  if (bus_num == 2) {
    // Bus 2→Bus 0: 仅 OP 激活时拦截 MPC 帧
    if (byd_op_tx_active) {
      if ((addr == BYD_ACC_MPC_STATE) ||
          (addr == BYD_ACC_HUD_ADAS) ||
          (addr == BYD_ACC_CMD) ||
          (addr == BYD_ACC_AEB)) {
        return true;
      }
    }
  }

  if (bus_num == 0) {
    // Bus 0→Bus 2: 拦截 OP 发的帧 (防止回传给 MPC)
    if ((addr == BYD_ACC_MPC_STATE) ||
        (addr == BYD_ACC_HUD_ADAS) ||
        (addr == BYD_ACC_CMD) ||
        (addr == BYD_ACC_AEB)) {
      return true;
    }
    // 792: 仅 OP 激活时拦截真实 EPS 的 792
    if (byd_op_tx_active && (addr == BYD_ACC_EPS_STATE)) {
      return true;
    }
  }

  return false;
}

static safety_config byd_init(uint16_t param) {
  byd_stock_longitudinal = GET_FLAG(param, BYD_PARAM_STOCK_LONGITUDINAL);
  byd_op_tx_active = false;
  byd_op_tx_last_ts = 0U;

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
    {BYD_ACC_MPC_STATE, BYD_MAIN_BUS, 8, .check_relay = false},
    {BYD_ACC_HUD_ADAS,  BYD_MAIN_BUS, 8, .check_relay = false},
    {BYD_ACC_CMD,        BYD_MAIN_BUS, 8, .check_relay = false},
    {BYD_ACC_AEB,        BYD_MAIN_BUS, 8, .check_relay = false},
    {BYD_ACC_EPS_STATE,  BYD_CAM_BUS,  8, .check_relay = false},
    {BYD_PCM_BUTTONS_FWD, BYD_CAM_BUS, 8, .check_relay = false},
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
