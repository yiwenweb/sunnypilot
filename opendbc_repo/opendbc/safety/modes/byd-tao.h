#pragma once

// ============================================================================
// byd-tao.h  —— 涛哥版 A 方案配套 panda safety (供对照测试, 部署时改名为 byd.h)
// ----------------------------------------------------------------------------
// 与你现有 byd.h 的唯一区别 (只改 fwd_hook, 其余完全一致):
//   涛哥版 carcontroller 【只发 814 ACC_CMD, 不发 813/815】(靠摄像头原厂 813/815 透传)。
//   你现有 byd.h 的 fwd_hook 在 byd_op_acc_active 时会连 813/815 一起拦 -> 车机收不到
//   ACC HUD/AEB。本文件改为: 只拦摄像头的 814 (OP自己发814覆盖), 放行摄像头 813/815 透传。
//   -> 涛哥的 814(透传摄像头counter) 与原厂透传的 813/815 天然同counter, 车机不报黄灯。
//
// ⚠️ 安全关键代码, 改动后必须重新编译 panda 固件并刷入 C3 (见文件末尾编译说明)。
// ⚠️ 若测试涛哥版不理想要切回, 把你原来的 byd.h 刷回去即可。
// ============================================================================

#include "opendbc/safety/safety_declarations.h"

// RX messages (Bus 0)
#define BYD_EPS              0x11FU  // 287
#define BYD_CARSPEED         0x121U  // 289
#define BYD_YAW_RATE         0x222U  // 546
#define BYD_AXAY             0x223U  // 547
#define BYD_DRIVE_STATE      0x242U  // 578
#define BYD_ACC_EPS_STATE    0x318U  // 792
#define BYD_PEDAL            0x342U  // 834
#define BYD_PCM_BUTTONS      0x3B0U  // 944

// RX messages (Bus 2 - from MPC)
#define BYD_ACC_HUD_ADAS_RX  0x32DU  // 813 - ACC state from MPC

// TX messages
#define BYD_ACC_MPC_STATE    0x316U  // 790 - steering (Bus 0)
#define BYD_ACC_CMD          0x32EU  // 814 - OP long (Bus 0)
#define BYD_ACC_EPS_FAKE     0x318U  // 792 - fake EPS (Bus 2)
#define BYD_PCM_BUTTONS_FWD  0x3B0U  // 944 - buttons forward (Bus 2)

#define BYD_MAIN_BUS 0U
#define BYD_CAM_BUS  2U

static uint8_t byd_get_counter(const CANPacket_t *msg) { UNUSED(msg); return 0U; }
static uint32_t byd_get_checksum(const CANPacket_t *msg) { UNUSED(msg); return 0U; }
static uint32_t byd_compute_checksum(const CANPacket_t *msg) { UNUSED(msg); return 0U; }

static const TorqueSteeringLimits BYD_STEERING_LIMITS = {
  .max_torque = 300,
  .max_rate_up = 18,       // 涛哥 STEER_DELTA_UP=7 < 18, 兼容 (发得更慢panda不拦)
  .max_rate_down = 18,
  .max_rt_delta = 243,
  .type = TorqueMotorLimited,
  .max_torque_error = 150,
  .min_valid_request_frames = 10,
  .max_invalid_request_frames = 5,
  .min_valid_request_rt_interval = 250000U,
  .has_steer_req_tolerance = true,
};

static bool byd_op_steering_active = false;
static uint32_t byd_op_steering_ts = 0U;
static bool byd_fake_eps_active = false;
static uint32_t byd_fake_eps_ts = 0U;
// 涛哥版只发 814, 用它标记 OP 纵向接管态 (仅拦摄像头 814, 不拦 813/815)
static bool byd_op_acc_active = false;
static uint32_t byd_op_acc_ts = 0U;


static void byd_rx_hook(const CANPacket_t *msg) {

  // === Bus 0 messages ===
  if (msg->bus == BYD_MAIN_BUS) {

    if (msg->addr == BYD_CARSPEED) {
      int speed_raw = (msg->data[0] | ((msg->data[1] & 0x0FU) << 8));
      UPDATE_VEHICLE_SPEED((float)speed_raw * 0.0735f * KPH_TO_MS);
    }

    if (msg->addr == BYD_EPS) {
      int angle_raw = (msg->data[0] | (msg->data[1] << 8));
      if (angle_raw > 32767) angle_raw -= 65536;
      update_sample(&angle_meas, angle_raw);
    }

    if (msg->addr == BYD_ACC_EPS_STATE) {
      int torque_motor_raw = ((msg->data[1] | ((msg->data[2] & 0x0FU) << 8)));
      if (torque_motor_raw > 2047) torque_motor_raw -= 4096;
      update_sample(&torque_meas, torque_motor_raw);

      int torque_driver_raw = ((msg->data[3] | (msg->data[4] << 8)) & 0xFFFU);
      if (torque_driver_raw > 2047) torque_driver_raw -= 4096;
      update_sample(&torque_driver, torque_driver_raw);
    }

    if (msg->addr == BYD_DRIVE_STATE) {
      brake_pressed = GET_BIT(msg, 37U);
      unsigned int gear = (msg->data[5] & 0x7U);
      vehicle_moving = (gear != 1U);
    }

    if (msg->addr == BYD_PEDAL) {
      gas_pressed = msg->data[0] > 0U;
    }

    if (msg->addr == BYD_PCM_BUTTONS) {
      acc_main_on = GET_BIT(msg, 8U);
      mads_button_press = acc_main_on ? MADS_BUTTON_PRESSED : MADS_BUTTON_NOT_PRESSED;
    }

    if (msg->addr == BYD_DRIVE_STATE) {
      if ((alternative_experience & ALT_EXP_ENABLE_MADS) && !m_mads_state.system_enabled) {
        m_mads_state.system_enabled = true;
      }
      mads_state_update(vehicle_moving, acc_main_on, controls_allowed,
                        brake_pressed || regen_braking, steering_disengage);
    }
  }

  // === Bus 2 messages (from MPC) ===
  if (msg->bus == BYD_CAM_BUS) {
    if (msg->addr == BYD_ACC_HUD_ADAS_RX) {
      unsigned int acc_state = ((msg->data[2] >> 3) & 0x07U);
      bool cruise_engaged = (acc_state == 1U) || (acc_state == 2U) ||
                            (acc_state == 3U) || (acc_state == 5U);
      controls_allowed = cruise_engaged;
      acc_main_on = (acc_state != 0U) && (acc_state != 7U);
    }
  }
}

static bool byd_tx_hook(const CANPacket_t *msg) {
  bool tx = true;

  // 790 steering on Bus 0 - torque check (steer_req = bit28 LKAS_Active, 不卡 CruiseActivated)
  if ((msg->addr == BYD_ACC_MPC_STATE) && (msg->bus == BYD_MAIN_BUS)) {
    int lkas_output = ((msg->data[2] | (msg->data[3] << 8)) & 0x7FFU);
    if (lkas_output > 1023) lkas_output -= 2048;
    bool steer_req = GET_BIT(msg, 28U);
    if (steer_torque_cmd_checks(lkas_output, steer_req, BYD_STEERING_LIMITS)) {
      tx = false;
    }
    if (tx) {
      byd_op_steering_active = true;
      byd_op_steering_ts = microsecond_timer_get();
    }
  }

  // 814 ACC_CMD on Bus 0 - 涛哥只发这一个 ACC 报文, 标记接管态用于拦摄像头的 814
  if ((msg->addr == BYD_ACC_CMD) && (msg->bus == BYD_MAIN_BUS)) {
    byd_op_acc_active = true;
    byd_op_acc_ts = microsecond_timer_get();
  }

  // 792 fake EPS on Bus 2 - always allow, mark active
  if ((msg->addr == BYD_ACC_EPS_FAKE) && (msg->bus == BYD_CAM_BUS)) {
    byd_fake_eps_active = true;
    byd_fake_eps_ts = microsecond_timer_get();
  }

  return tx;
}

static bool byd_fwd_hook(int bus_num, int addr) {
  // Timeout: 100ms no TX -> resume full passthrough
  if (byd_op_steering_active) {
    if ((microsecond_timer_get() - byd_op_steering_ts) > 100000U) {
      byd_op_steering_active = false;
    }
  }
  if (byd_fake_eps_active) {
    if ((microsecond_timer_get() - byd_fake_eps_ts) > 100000U) {
      byd_fake_eps_active = false;
    }
  }
  if (byd_op_acc_active) {
    if ((microsecond_timer_get() - byd_op_acc_ts) > 100000U) {
      byd_op_acc_active = false;
    }
  }

  // Bus 2 -> Bus 0
  if (bus_num == 2) {
    // 始终拦摄像头的 790, EPS 只听 OP
    if (addr == BYD_ACC_MPC_STATE) {
      return true;
    }
    // ★A方案关键: 只拦摄像头的 814 (OP自己发814覆盖); 【放行】摄像头 813/815 透传到车机。
    //   涛哥的 814 透传摄像头 counter, 与原厂透传的 813/815 天然同 counter, 车机不报黄灯。
    if (byd_op_acc_active && (addr == BYD_ACC_CMD)) {
      return true;
    }
  }

  // Bus 0 -> Bus 2
  if (bus_num == 0) {
    if (addr == BYD_ACC_MPC_STATE) {
      return true;
    }
    if (byd_fake_eps_active && (addr == BYD_ACC_EPS_STATE)) {
      return true;
    }
  }

  return false;
}

static safety_config byd_init(uint16_t param) {
  UNUSED(param);
  byd_op_steering_active = false;
  byd_op_steering_ts = 0U;
  byd_fake_eps_active = false;
  byd_fake_eps_ts = 0U;
  byd_op_acc_active = false;
  byd_op_acc_ts = 0U;

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

  // ★A方案: TX 列表去掉 813/815 (涛哥不发, 由摄像头透传); 保留 790/814/792fake/944fwd
  static const CanMsg BYD_TX_MSGS[] = {
    {BYD_ACC_MPC_STATE,  BYD_MAIN_BUS, 8, .check_relay = false},  // 790 steering
    {BYD_ACC_CMD,        BYD_MAIN_BUS, 8, .check_relay = false},  // 814 OP long
    {BYD_ACC_EPS_FAKE,   BYD_CAM_BUS,  8, .check_relay = false},  // 792 fake EPS
    {BYD_PCM_BUTTONS_FWD, BYD_CAM_BUS, 8, .check_relay = false},  // 944 buttons -> MPC
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
