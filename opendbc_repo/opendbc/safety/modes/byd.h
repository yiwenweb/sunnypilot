#pragma once

#include "opendbc/safety/safety_declarations.h"

// Safety-relevant CAN messages for BYD vehicles (Tang DM 2018 and similar)
// Based on byd_tang_dm_2018.dbc

// RX messages (from vehicle ECUs)
#define BYD_EPS              0x11FU  // 287 - Steering angle and rate from EPS
#define BYD_CARSPEED         0x121U  // 289 - Vehicle speed display
#define BYD_YAW_RATE         0x222U  // 546 - Yaw rate from ESP
#define BYD_DRIVE_STATE      0x242U  // 578 - Gear, brake pedal from VCU
#define BYD_ACC_EPS_STATE    0x318U  // 792 - EPS feedback, driver torque
#define BYD_ACC_HUD_ADAS     0x32DU  // 813 - ACC state and HUD
#define BYD_PEDAL            0x342U  // 834 - Accelerator and brake pedal
#define BYD_PCM_BUTTONS      0x3B0U  // 944 - Cruise control buttons

// TX messages (from openpilot)
#define BYD_ACC_MPC_STATE    0x316U  // 790 - LKAS control output
#define BYD_ACC_CMD          0x32EU  // 814 - ACC acceleration command

// CAN bus numbers
#define BYD_MAIN_BUS 0U

// Checksum calculation: BYD uses simple byte-sum checksum
// CHECKSUM = sum(data[0:7]) & 0xFF
static uint32_t byd_compute_checksum(const CANPacket_t *msg) {
  uint8_t checksum = 0U;
  for (int i = 0; i < 7; i++) {
    checksum += msg->data[i];
  }
  return checksum;
}

static uint32_t byd_get_checksum(const CANPacket_t *msg) {
  return msg->data[7];
}

static uint8_t byd_get_counter(const CANPacket_t *msg) {
  uint8_t cnt = 0U;
  if (msg->addr == BYD_EPS) {
    // 8-bit counter at bits 32-39
    cnt = msg->data[4];
  } else if ((msg->addr == BYD_YAW_RATE) || (msg->addr == BYD_DRIVE_STATE) ||
             (msg->addr == BYD_ACC_EPS_STATE) || (msg->addr == BYD_ACC_HUD_ADAS) ||
             (msg->addr == BYD_PCM_BUTTONS)) {
    // 4-bit counter at bits 48-51
    cnt = msg->data[6] & 0xFU;
  }
  return cnt;
}

// LKAS steering limits for BYD
// LKAS_Output is 11-bit signed, range [-1024, 1023]
static const TorqueSteeringLimits BYD_STEERING_LIMITS = {
  .max_torque = 300,              // conservative limit for safety
  .max_rate_up = 10,              // torque increase per cycle
  .max_rate_down = 25,            // torque decrease per cycle
  .max_rt_delta = 128,            // max change per 250ms
  .type = TorqueDriverLimited,

  .driver_torque_allowance = 80,
  .driver_torque_multiplier = 3,

  .max_torque_error = 350,

  .min_valid_request_frames = 10,
  .max_invalid_request_frames = 5,
  .min_valid_request_rt_interval = 250000U,
  .has_steer_req_tolerance = true,
};

static void byd_rx_hook(const CANPacket_t *msg) {
  if (msg->bus == BYD_MAIN_BUS) {
    // Update vehicle speed from CARSPEED (289)
    // Signal: CarDisplaySpeed - 12-bit unsigned, scale 1 km/h
    if (msg->addr == BYD_CARSPEED) {
      int speed_kph = (msg->data[0] | ((msg->data[1] & 0x0FU) << 8));
      UPDATE_VEHICLE_SPEED((float)speed_kph * KPH_TO_MS);
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

    // Update cruise state from ACC_HUD_ADAS (813)
    // Signal: AccState - 3 bits at bits 19-21
    // 0=OFF, 2=ACC_ON, 3=ACC_ACTIVE, 5=FORCE_ACCEL, 7=ERROR
    if (msg->addr == BYD_ACC_HUD_ADAS) {
      unsigned int acc_state = (msg->data[2] >> 3) & 0x7U;
      bool cruise_engaged = (acc_state == 3U);  // ACC_ACTIVE
      pcm_cruise_check(cruise_engaged);
      acc_main_on = (acc_state == 2U) || cruise_engaged;  // ACC_ON or ACC_ACTIVE
    }

    // Update vehicle moving state from DRIVE_STATE (578)
    // Signal: Gear - 3 bits at bits 40-42
    // 1=P, 2=R, 3=N, 4=D
    if (msg->addr == BYD_DRIVE_STATE) {
      unsigned int gear = (msg->data[5] & 0x7U);
      // Vehicle is moving if not in Park
      vehicle_moving = (gear != 1U);
    }

    // Check for MADS button from PCM_BUTTONS (944)
    if (msg->addr == BYD_PCM_BUTTONS) {
      // BTN_TOGGLE_ACC_OnOff at bit 8
      mads_button_press = GET_BIT(msg, 8U) ? MADS_BUTTON_PRESSED : MADS_BUTTON_NOT_PRESSED;
    }
  }
}

static bool byd_tx_hook(const CANPacket_t *msg) {
  bool tx = true;

  // Safety check for ACC_MPC_STATE (790) - LKAS control
  if (msg->addr == BYD_ACC_MPC_STATE) {
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

  // Safety check for ACC_CMD (814) - Longitudinal control
  if (msg->addr == BYD_ACC_CMD) {
    // Signal: AccelCmd - 8-bit, scale 0.05, offset -5, range [-5, 7.75] m/s^2
    // Raw value 0 = -5 m/s^2, raw value 100 = 0 m/s^2, raw value 255 = 7.75 m/s^2
    int accel_raw = msg->data[0];

    // Signal: AccControlActive - 1 bit at bit 44
    bool acc_active = GET_BIT(msg, 44U);

    // Define longitudinal limits
    // accel_raw = (accel_m_s2 + 5) / 0.05
    // So: -3.5 m/s^2 -> raw 30, +2.0 m/s^2 -> raw 140
    const int BYD_MAX_ACCEL_RAW = 140U;   // +2.0 m/s^2
    const int BYD_MIN_ACCEL_RAW = 30U;    // -3.5 m/s^2
    const int BYD_INACTIVE_ACCEL_RAW = 100U;  // 0 m/s^2

    bool violation = false;

    // Check accel limits when active
    if (acc_active) {
      violation |= (accel_raw > BYD_MAX_ACCEL_RAW) || (accel_raw < BYD_MIN_ACCEL_RAW);
    } else {
      // When inactive, accel should be near zero
      violation |= (accel_raw != BYD_INACTIVE_ACCEL_RAW);
    }

    // Don't allow longitudinal control if not allowed
    violation |= acc_active && !get_longitudinal_allowed();

    if (violation) {
      tx = false;
    }
  }

  return tx;
}

static safety_config byd_init(uint16_t param) {
  UNUSED(param);

  static RxCheck byd_rx_checks[] = {
    // EPS (287) - 50ms cycle, 8-bit counter
    {.msg = {{BYD_EPS, 0, 5, 20U, .max_counter = 255U, .ignore_checksum = true}, { 0 }, { 0 }}},
    // CARSPEED (289) - 50ms cycle, no counter/checksum
    {.msg = {{BYD_CARSPEED, 0, 8, 20U, .ignore_checksum = true, .ignore_counter = true, .ignore_quality_flag = true}, { 0 }, { 0 }}},
    // DRIVE_STATE (578) - 50ms cycle, 4-bit counter
    {.msg = {{BYD_DRIVE_STATE, 0, 8, 20U, .max_counter = 15U}, { 0 }, { 0 }}},
    // ACC_EPS_STATE (792) - 50ms cycle, 4-bit counter
    {.msg = {{BYD_ACC_EPS_STATE, 0, 8, 20U, .max_counter = 15U}, { 0 }, { 0 }}},
    // ACC_HUD_ADAS (813) - 50ms cycle, 4-bit counter
    {.msg = {{BYD_ACC_HUD_ADAS, 0, 8, 20U, .max_counter = 15U}, { 0 }, { 0 }}},
    // PEDAL (834) - 50ms cycle
    {.msg = {{BYD_PEDAL, 0, 8, 20U, .ignore_counter = true}, { 0 }, { 0 }}},
    // PCM_BUTTONS (944) - 50ms cycle, 4-bit counter
    {.msg = {{BYD_PCM_BUTTONS, 0, 8, 20U, .max_counter = 15U}, { 0 }, { 0 }}},
  };

  static const CanMsg BYD_TX_MSGS[] = {
    // ACC_MPC_STATE (790) - LKAS control, check relay malfunction
    {BYD_ACC_MPC_STATE, 0, 8, .check_relay = true},
    // ACC_CMD (814) - ACC control, check relay malfunction
    {BYD_ACC_CMD, 0, 8, .check_relay = true},
  };

  return BUILD_SAFETY_CFG(byd_rx_checks, BYD_TX_MSGS);
}

const safety_hooks byd_hooks = {
  .init = byd_init,
  .rx = byd_rx_hook,
  .tx = byd_tx_hook,
  .get_counter = byd_get_counter,
  .get_checksum = byd_get_checksum,
  .compute_checksum = byd_compute_checksum,
};
