"""
BYD CAN message generation - lateral only (stock longitudinal).
Based on carrotpilot by yysnet.

Only 790 (steering) and 792 (fake EPS feedback) are generated.
813/814/815 are left to stock MPC passthrough.
"""

from opendbc.car.byd.values import CanBus


def byd_checksum(dat):
    """Nibble CRC checksum (byte_key=0xAF) - from carrotpilot, verified working."""
    byte_key = 0xAF
    first_bytes_sum = sum(byte >> 4 for byte in dat)
    second_bytes_sum = sum(byte & 0xF for byte in dat)
    remainder = second_bytes_sum >> 4
    second_bytes_sum += byte_key >> 4
    first_bytes_sum += byte_key & 0xF
    first_part = ((-first_bytes_sum + 0x9) & 0xF)
    second_part = ((-second_bytes_sum + 0x9) & 0xF)
    return (((first_part + (-remainder + 5)) << 4) + second_part) & 0xFF


def create_steering_control(packer, cam_msg, apply_torque, req_prepare, active, hud_control, counter):
    """790 ACC_MPC_STATE -> Bus 0 -> EPS. Passthrough stock MPC signals, override control fields."""
    values = {s: cam_msg[s] for s in [
        "AutoFullBeamState", "LeftLaneState", "LKAS_Config", "SETME2_0x1",
        "MPC_State", "AutoFullBeam_OnOff", "LKAS_Output", "LKAS_Active",
        "SETME3_0x0", "TrafficSignRecognition_OnOff", "SETME4_0x0", "SETME5_0x1",
        "RightLaneState", "LKAS_State", "TrafficSignRecognition_Result",
        "LKAS_AlarmType", "SETME7_0x3",
    ]}

    values["ReqHandsOnSteeringWheel"] = 0
    values["LKAS_ReqPrepare"] = req_prepare
    values["COUNTER"] = counter
    values["CHECKSUM"] = 0

    if active:
        mpc_state = values["MPC_State"]
        values.update({
            "LKAS_Output": apply_torque,
            "LKAS_Active": 1,
            "LKAS_State": 4 if (mpc_state == 2) else 2,
            "LeftLaneState": 3 if hud_control.leftLaneDepart else int(hud_control.leftLaneVisible) + 1,
            "RightLaneState": 3 if hud_control.rightLaneDepart else int(hud_control.rightLaneVisible) + 1,
        })
    else:
        values.update({
            "LKAS_Output": 0,
            "LKAS_Active": 0,
        })

    data = packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(data)
    return packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)


def create_fake_eps(packer, esc_msg, fake_torque, lkas_reqprepare, lkas_active, enabled, counter):
    """792 ACC_EPS_STATE -> Bus 2 -> MPC. Trick MPC so AEB/safety features keep working."""
    values = {s: esc_msg[s] for s in [
        "LKAS_Prepared", "CruiseActivated", "TorqueFailed", "SETME1_0x1",
        "SteerWarning", "SteerErrorCode", "MainTorque", "SETME3_0x1",
        "SETME4_0x3", "SteerDriverTorque", "SETME5_0xFF", "SETME6_0xFFF",
    ]}

    values["ReportHandsNotOnSteeringWheel"] = 0

    if enabled:
        if lkas_active:
            values.update({"LKAS_Prepared": 0, "CruiseActivated": 1, "MainTorque": fake_torque})
        elif lkas_reqprepare:
            values.update({"LKAS_Prepared": 1, "CruiseActivated": 0, "MainTorque": 0})
        else:
            values.update({"LKAS_Prepared": 0, "CruiseActivated": 0, "MainTorque": 0})

    msg = packer.make_can_msg("ACC_EPS_STATE", CanBus.CAM, values)
    dat = bytearray(msg[1])
    # 792 counter in HIGH nibble of byte[6], SETME=0xF in LOW nibble
    dat[6] = ((counter & 0xF) << 4) | 0xF
    dat[7] = byd_checksum(dat)
    return (msg[0], bytes(dat), msg[2])
