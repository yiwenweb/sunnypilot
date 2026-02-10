#!/usr/bin/env python3
"""解码 cabana 截图中的 CAN 数据"""

def decode_790(data_hex):
    """解码 ACC_MPC_STATE (790)"""
    dat = bytes.fromhex(data_hex.replace(' ', ''))
    print(f"\n=== 790 ACC_MPC_STATE: {data_hex} ===")
    
    # byte 0
    auto_fullbeam_state = dat[0] & 0x0F
    left_lane = (dat[0] >> 4) & 0x03
    lkas_config = (dat[0] >> 6) & 0x03
    print(f"  AutoFullBeamState={auto_fullbeam_state}, LeftLane={left_lane}, LKAS_Config={lkas_config}")
    
    # byte 1
    setme2 = dat[1] & 0x03
    req_hands = (dat[1] >> 2) & 1
    mpc_state = (dat[1] >> 3) & 0x0F
    auto_fullbeam = (dat[1] >> 7) & 1
    print(f"  SETME2={setme2}, ReqHands={req_hands}, MPC_State={mpc_state}, AutoFullBeam={auto_fullbeam}")
    
    # byte 2-3: LKAS_Output (11-bit signed at bits 16-26)
    raw16 = dat[2] | (dat[3] << 8)
    lkas_output = raw16 & 0x7FF
    if lkas_output > 1023:
        lkas_output -= 2048
    req_prepare = (raw16 >> 11) & 1
    lkas_active = (raw16 >> 12) & 1
    setme3 = (dat[3] >> 5) & 1
    tsr_onoff = (dat[3] >> 6) & 1
    setme4 = (dat[3] >> 7) & 1
    print(f"  LKAS_Output={lkas_output}, ReqPrepare={req_prepare}, Active={lkas_active}")
    print(f"  SETME3={setme3}, TSR_OnOff={tsr_onoff}, SETME4={setme4}")
    
    # byte 4
    setme5 = dat[4] & 0x03
    right_lane = (dat[4] >> 2) & 0x03
    lkas_state = (dat[4] >> 4) & 0x0F
    print(f"  SETME5={setme5}, RightLane={right_lane}, LKAS_State={lkas_state}")
    
    # byte 5
    tsr_result = dat[5]
    print(f"  TSR_Result_raw={tsr_result} ({tsr_result * 5 - 5} km/h)")
    
    # byte 6
    lkas_alarm = (dat[6] >> 1) & 0x03
    setme7 = (dat[6] >> 3) & 0x03
    counter = (dat[6] >> 4) & 0x0F
    print(f"  AlarmType={lkas_alarm}, SETME7={setme7}, Counter={counter}")
    
    # byte 7
    print(f"  Checksum=0x{dat[7]:02X}")

def decode_792(data_hex):
    """解码 ACC_EPS_STATE (792)"""
    dat = bytes.fromhex(data_hex.replace(' ', ''))
    print(f"\n=== 792 ACC_EPS_STATE: {data_hex} ===")
    
    # byte 0
    lkas_prepared = dat[0] & 1
    cruise_activated = (dat[0] >> 1) & 1
    torque_failed = (dat[0] >> 2) & 1
    setme1 = (dat[0] >> 3) & 1
    steer_warning = (dat[0] >> 4) & 1
    steer_error = (dat[0] >> 5) & 0x07
    print(f"  LKAS_Prepared={lkas_prepared}, CruiseActivated={cruise_activated}")
    print(f"  TorqueFailed={torque_failed}, SETME1={setme1}")
    print(f"  SteerWarning={steer_warning}, SteerErrorCode={steer_error}")
    
    # byte 1-2: MainTorque (12-bit signed at bits 8-19)
    raw16 = dat[1] | (dat[2] << 8)
    main_torque = raw16 & 0xFFF
    if main_torque > 2047:
        main_torque -= 4096
    setme3 = (raw16 >> 12) & 1
    report_hands = (raw16 >> 13) & 1
    setme4 = (raw16 >> 14) & 0x03
    print(f"  MainTorque={main_torque}")
    print(f"  SETME3={setme3}, ReportHands={report_hands}, SETME4={setme4}")
    
    # byte 3-4: SteerDriverTorque (12-bit signed at bits 24-35)
    raw16b = dat[3] | (dat[4] << 8)
    driver_torque = raw16b & 0xFFF
    if driver_torque > 2047:
        driver_torque -= 4096
    print(f"  SteerDriverTorque={driver_torque}")
    
    # byte 4 upper + byte 5
    setme5 = (dat[4] >> 4) & 0x0F
    setme6 = dat[5] | ((dat[6] & 0x0F) << 8)
    print(f"  SETME5=0x{setme5:X}, SETME6=0x{setme6:03X}")
    
    # byte 6-7
    print(f"  byte6=0x{dat[6]:02X}, byte7(checksum)=0x{dat[7]:02X}")

def decode_814(data_hex):
    """解码 ACC_CMD (814)"""
    dat = bytes.fromhex(data_hex.replace(' ', ''))
    print(f"\n=== 814 ACC_CMD: {data_hex} ===")
    
    accel_raw = dat[0]
    accel = accel_raw * 0.05 - 5
    comfort_upper = dat[1] * 0.05 - 5
    comfort_lower = dat[2] * 0.05 - 5
    jerk_upper = (dat[3] & 0x7F) * 0.2
    setme1 = (dat[3] >> 7) & 1
    jerk_lower = (dat[4] & 0x7F) * 0.2 - 16
    resume = (dat[4] >> 7) & 1
    standstill = (dat[5] >> 0) & 1
    brake_behav = (dat[5] >> 1) & 0x03
    acc_req = (dat[5] >> 3) & 1
    acc_active = (dat[5] >> 4) & 1
    acc_override = (dat[5] >> 5) & 1
    esp_behav = (dat[5] >> 6) & 0x03
    counter = (dat[6] >> 0) & 0x0F
    setme2 = (dat[6] >> 4) & 0x0F
    
    print(f"  AccelCmd={accel:.2f} m/s^2 (raw={accel_raw})")
    print(f"  ComfortUpper={comfort_upper:.2f}, ComfortLower={comfort_lower:.2f}")
    print(f"  JerkUpper={jerk_upper:.1f}, JerkLower={jerk_lower:.1f}")
    print(f"  SETME1={setme1}, Resume={resume}")
    print(f"  Standstill={standstill}, BrakeBehav={brake_behav}")
    print(f"  AccReqNotStandstill={acc_req}, AccControlActive={acc_active}")
    print(f"  AccOverride={acc_override}, EspBehav={esp_behav}")
    print(f"  Counter={counter}, SETME2=0x{setme2:X}")

def decode_815(data_hex):
    """解码 ACC_AEB (815)"""
    dat = bytes.fromhex(data_hex.replace(' ', ''))
    print(f"\n=== 815 ACC_AEB: {data_hex} ===")
    
    aeb_active = dat[0] & 1
    aeb_decel = dat[1] * 0.05
    counter = dat[6] & 0x0F
    setme = (dat[6] >> 4) & 0x0F
    
    print(f"  AEB_Active={aeb_active}")
    print(f"  AEB_Decel={aeb_decel:.2f} m/s^2")
    print(f"  Counter={counter}, SETME=0x{setme:X}")

print("=" * 60)
print("从 cabana 截图解码 CAN 数据")
print("=" * 60)

# 790 - 原厂 MPC (bus 2)
decode_790("42 81 00 40 71 09 BC C6")

# 790 - 转发到 bus 0 后返回 (bus 128)
decode_790("62 81 0C 50 79 09 BC 82")

# 790 - bus 197 (rejected?)
decode_790("62 81 00 40 79 09 DC 7E")

# 792 - EPS 回复 (bus 0)
decode_792("FA 11 F0 40 FF FF 0F B7")

# 814 - ACC_CMD (bus 2)
decode_814("64 64 64 80 50 50 FA B9")

# 815 - ACC_AEB (bus 2)
decode_815("05 80 02 0F FF FF FA 71")

# 813 - ACC_HUD_ADAS (bus 2)
print("\n=== 813 ACC_HUD_ADAS: 00 86 44 01 F4 FF FA 37 ===")
dat = bytes.fromhex("00 86 44 01 F4 FF FA 37".replace(' ', ''))
raw16 = dat[0] | (dat[1] << 8)
set_speed = raw16 & 0x1FF
has_lead = (raw16 >> 9) & 1
set_dist = (raw16 >> 10) & 0x07
lead_dist = (raw16 >> 13) & 0x07
print(f"  SetSpeed={set_speed * 0.5} km/h, HasLead={has_lead}")
print(f"  SetDistance={set_dist}, LeadingDistance={lead_dist}")
aeb = dat[2] & 1
fcw = (dat[2] >> 1) & 1
setme1 = (dat[2] >> 2) & 1
acc_state = (dat[2] >> 3) & 0x07
acc_on1 = (dat[2] >> 6) & 1
close_warn = (dat[2] >> 7) & 1
print(f"  AEB={aeb}, FCW={fcw}, SETME1={setme1}")
print(f"  AccState={acc_state}, AccOn1={acc_on1}, CloseWarning={close_warn}")
