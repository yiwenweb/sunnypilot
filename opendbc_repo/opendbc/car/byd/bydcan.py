"""
BYD CAN message generation module.

核心改动 (参考涛哥 carrotpilot):
  所有 create_xxx 函数接收原厂帧信号字典 (cam_msg / esc_msg)，
  先复制原厂所有信号值，再只修改需要改的控制字段。
  这确保 EPS/ESP 看到的帧与原厂 MPC 帧高度一致，
  只有控制相关字段被替换。

checksum 算法:
  涛哥用 nibble-based CRC (byte_key=0xAF)。
  我们的简单算法 (0xFF - sum) 在实车嗅探中验证过。
  两种算法可能对同一数据产生相同结果。
  保留涛哥的算法作为备选，默认仍用我们验证过的。
"""

import numpy as np
from opendbc.car.byd.values import CanBus


def byd_checksum(dat: bytes) -> int:
    """我们验证过的简单 checksum"""
    return (0xFF - sum(dat[:7])) & 0xFF


def byd_checksum_nibble(byte_key, dat):
    """涛哥的 nibble CRC checksum (byte_key=0xAF)"""
    first_bytes_sum = sum(byte >> 4 for byte in dat)
    second_bytes_sum = sum(byte & 0xF for byte in dat)
    remainder = second_bytes_sum >> 4
    second_bytes_sum += byte_key >> 4
    first_bytes_sum += byte_key & 0xF
    first_part = ((-first_bytes_sum + 0x9) & 0xF)
    second_part = ((-second_bytes_sum + 0x9) & 0xF)
    return (((first_part + (-remainder + 5)) << 4) + second_part) & 0xFF


def create_steering_control(packer, CP, cam_msg: dict, apply_torque: int,
                            req_prepare: bool, active: bool, hud_control, counter: int):
    """
    生成转向控制报文 (ACC_MPC_STATE - 790)

    关键: 先复制原厂 MPC 的所有信号值，再只修改控制字段。
    这确保 EPS 看到的帧与原厂高度一致。

    参数:
        cam_msg: 原厂 MPC 790 帧的信号值字典 (从 CS.cam_lkas)
    """
    # 从原厂 MPC 帧复制所有信号值
    values = {s: cam_msg[s] for s in [
        "AutoFullBeamState",
        "LeftLaneState",
        "LKAS_Config",
        "SETME2_0x1",
        "MPC_State",
        "AutoFullBeam_OnOff",
        "LKAS_Output",
        "LKAS_Active",
        "SETME3_0x0",
        "TrafficSignRecognition_OnOff",
        "SETME4_0x0",
        "SETME5_0x1",
        "RightLaneState",
        "LKAS_State",
        "TrafficSignRecognition_Result",
        "LKAS_AlarmType",
        "SETME7_0x3",
    ] if s in cam_msg}

    # 只修改控制字段
    values["ReqHandsOnSteeringWheel"] = 0
    values["LKAS_ReqPrepare"] = 1 if req_prepare else 0
    values["COUNTER"] = counter
    values["CHECKSUM"] = 0

    if active:
        mpc_state = values.get("MPC_State", 0)
        values.update({
            "LKAS_Output": apply_torque,
            "LKAS_Active": 1,
            # 涛哥: LKAS_State = 4 if mpc cancelling else 2
            "LKAS_State": 4 if (mpc_state == 2) else 2,
            "LeftLaneState": 3 if hud_control.leftLaneDepart else (int(hud_control.leftLaneVisible) + 1),
            "RightLaneState": 3 if hud_control.rightLaneDepart else (int(hud_control.rightLaneVisible) + 1),
        })
    else:
        values.update({
            "LKAS_Output": 0,
            "LKAS_Active": 0,
        })

    data = packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(data)

    return packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)


def create_acc_cmd(packer, CP, CS, cam_msg: dict, mrr_lead_dist: float, accel: float,
                   resume_from_standstill: bool, standstill_state: bool, long_active: bool,
                   acc_on: bool = False, lat_active: bool = False, counter: int = 0):
    """
    生成 ACC 控制指令报文 (ACC_CMD - 814)

    关键: 先复制原厂 MPC 的所有信号值，再只修改控制字段。
    """
    K_jerk_xp = [10, 30, 50, 100]
    K_jerk_base_upper_fp = [2.0, 1.5, 1.0, 0.8]
    K_jerk_base_lower_fp = [3.0, 2.5, 2.0, 1.5]
    K_accel_jerk_upper = 0.3
    K_accel_jerk_lower = 0.5

    # 从原厂 MPC 帧复制所有信号值
    values = {s: cam_msg[s] for s in [
        "AccelCmd",
        "ComfortBandUpper",
        "ComfortBandLower",
        "JerkUpperLimit",
        "SETME1_0x1",
        "JerkLowerLimit",
        "ResumeFromStandstill",
        "StandstillState",
        "BrakeBehaviour",
        "AccReqNotStandstill",
        "AccControlActive",
        "AccOverrideOrStandstill",
        "EspBehaviour",
        "SETME2_0xF",
    ] if s in cam_msg}

    values["COUNTER"] = counter
    values["CHECKSUM"] = 0

    if long_active:
        jerk_base_upper = np.interp(mrr_lead_dist, K_jerk_xp, K_jerk_base_upper_fp)
        jerk_base_lower = np.interp(mrr_lead_dist, K_jerk_xp, K_jerk_base_lower_fp)
        if accel < 0:
            jerk_upper = jerk_base_upper
            jerk_lower = jerk_base_lower + accel * K_accel_jerk_lower
        else:
            jerk_upper = jerk_base_upper + accel * K_accel_jerk_upper
            jerk_lower = jerk_base_lower
        jerk_upper = max(0.2, min(12.7, jerk_upper))
        jerk_lower = max(-16.0, min(12.7, jerk_lower))
        limited_accel = max(-5.0, min(7.75, accel))

        values.update({
            "AccelCmd": limited_accel,
            "ComfortBandUpper": 0.05,
            "ComfortBandLower": 0.05,
            "JerkUpperLimit": jerk_upper,
            "JerkLowerLimit": jerk_lower,
            "ResumeFromStandstill": 1 if resume_from_standstill else 0,
            "StandstillState": 1 if standstill_state else 0,
        })
    # 非激活时: 保持原厂 MPC 的值不变 (透传)

    data = packer.make_can_msg("ACC_CMD", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(data)

    return packer.make_can_msg("ACC_CMD", CanBus.PT, values)


def create_acc_hud(packer, CP, CS, cam_msg: dict, set_speed: float, has_lead: bool,
                   set_distance: int, acc_on: bool = False, lat_active: bool = False,
                   long_active: bool = False, counter: int = 0):
    """
    生成 ACC HUD 显示报文 (ACC_HUD_ADAS - 813)

    关键: 先复制原厂 MPC 的所有信号值，再只修改显示字段。
    """
    # 从原厂 MPC 帧复制所有信号值
    values = {s: cam_msg[s] for s in [
        "SetSpeed",
        "HasLead",
        "SetDistance",
        "LeadingDistance",
        "AEB",
        "FCW",
        "SETME1_0x1",
        "AccState",
        "AccOn1",
        "CloseWarning",
        "SETME2_0x1",
        "Notify",
        "Status",
        "SETME3_0xFFF",
        "SETME4_0xF",
    ] if s in cam_msg}

    values["COUNTER"] = counter
    values["CHECKSUM"] = 0

    # 非激活时完全透传原厂值，不做任何修改
    # 激活时也尽量保持原厂值，只修改必要的显示字段
    # (原厂 MPC 的 AccState/AccOn1 等已经正确反映 ACC 状态)

    data = packer.make_can_msg("ACC_HUD_ADAS", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(data)

    return packer.make_can_msg("ACC_HUD_ADAS", CanBus.PT, values)


def create_fake_eps_feedback(packer, esc_msg: dict, fake_torque: int,
                             lkas_req_prepare: bool, lkas_active: bool, enabled: bool,
                             counter: int = 0):
    """
    生成 EPS 反馈欺骗报文 (ACC_EPS_STATE - 792) 发到 Bus 2

    关键: 先复制真实 EPS 的所有信号值，再只修改控制字段。
    这确保 MPC 看到的 792 与真实 EPS 高度一致。
    """
    # 从真实 EPS 帧复制所有信号值
    values = {s: esc_msg[s] for s in [
        "LKAS_Prepared",
        "CruiseActivated",
        "TorqueFailed",
        "SETME1_0x1",
        "SteerWarning",
        "SteerErrorCode",
        "MainTorque",
        "SETME3_0x1",
        "SETME4_0x3",
        "SteerDriverTorque",
        "SETME5_0xFF",
        "SETME6_0xFFF",
    ] if s in esc_msg}

    values["ReportHandsNotOnSteeringWheel"] = 0

    if enabled:
        if lkas_active:
            values.update({
                "LKAS_Prepared": 0,
                "CruiseActivated": 1,
                "MainTorque": fake_torque,
            })
        elif lkas_req_prepare:
            values.update({
                "LKAS_Prepared": 1,
                "CruiseActivated": 0,
                "MainTorque": 0,
            })
        else:
            values.update({
                "LKAS_Prepared": 0,
                "CruiseActivated": 0,
                "MainTorque": 0,
            })

    msg = packer.make_can_msg("ACC_EPS_STATE", CanBus.CAM, values)
    dat = bytearray(msg[1])
    # 手动填充 counter 和 checksum
    dat[6] = ((counter & 0xF) << 4) | 0xF
    dat[7] = byd_checksum(dat)
    return (msg[0], bytes(dat), msg[2])
