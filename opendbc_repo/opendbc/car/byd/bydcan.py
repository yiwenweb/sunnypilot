"""
BYD CAN message generation module.

This module provides functions to create CAN messages for BYD vehicles,
including steering control, ACC commands, and HUD display messages.
"""

import numpy as np

from opendbc.car.byd.values import CanBus


def byd_checksum(byte_key: int, dat: bytes) -> int:
    """
    计算BYD CAN报文校验和
    算法: 基于字节高低4位分别求和后取反
    注意: 计算时 byte 7 (checksum位) 必须为 0
    """
    # Ensure byte 7 is 0 for calculation
    if len(dat) >= 8:
        dat = dat[:7] + b'\x00'
    first_bytes_sum = sum(byte >> 4 for byte in dat)
    second_bytes_sum = sum(byte & 0xF for byte in dat)
    remainder = second_bytes_sum >> 4
    second_bytes_sum += byte_key >> 4
    first_bytes_sum += byte_key & 0xF
    first_part = ((-first_bytes_sum + 0x9) & 0xF)
    second_part = ((-second_bytes_sum + 0x9) & 0xF)
    return (((first_part + (-remainder + 5)) << 4) + second_part) & 0xFF


def create_steering_control(packer, CP, CS, req_torque: int, req_prepare: bool,
                            active: bool, hud_control, counter: int):
    """
    生成转向控制报文 (ACC_MPC_STATE - 0x316)
    MPC -> Panda -> EPS

    参数:
        packer: CAN打包器
        CP: 车辆参数
        CS: 车辆状态
        req_torque: 请求的转向扭矩 (-1500 ~ 1500)
        req_prepare: 是否请求准备状态
        active: LKAS是否激活
        hud_control: HUD控制信息
        counter: 报文计数器 (0-15)
    """
    # 原厂 MPC 空闲 790 raw: 42 81 00 40 71 00 xC CC
    # 解码: AutoBeam=2, LeftLane=0(GRAY), Config=1(ALARM),
    #        SETME2=1, MPC_State=0, AutoFullBeam_OnOff=1,
    #        LKAS_Output=0, ReqPrepare=0, Active=0,
    #        SETME5=1, RightLane=0(GRAY), LKAS_State=7
    # 关键差异: Config=1(不是3), LKAS_State=7(不是0), AutoFullBeam=1(不是0),
    #           LaneState=0/GRAY(不是1/GREEN)
    values = {
        "AutoFullBeamState": 2,       # AutoFullBeamInactive (和原厂一致)
        "LeftLaneState": 0,           # GRAY (原厂空闲=0, 不是GREEN=1)
        "LKAS_Config": 1,             # ALARM (原厂=1, 不是 ALARM_AND_LKA=3)
        "SETME2_0x1": 1,
        "ReqHandsOnSteeringWheel": 0,
        "MPC_State": 0,
        "AutoFullBeam_OnOff": 1,      # 原厂=1 (不是0)
        "LKAS_Output": 0,
        "LKAS_ReqPrepare": 0,
        "LKAS_Active": 0,
        "SETME3_0x0": 0,
        "TrafficSignRecognition_OnOff": 0,
        "SETME4_0x0": 0,
        "SETME5_0x1": 1,
        "RightLaneState": 0,          # GRAY (原厂空闲=0)
        "LKAS_State": 7,              # 原厂空闲=7 (不是0)
        "TrafficSignRecognition_Result": 0,
        "LKAS_AlarmType": 0,
        "SETME7_0x3": 3,
        "COUNTER": counter,
    }

    # 更新LKAS控制值
    values["LKAS_ReqPrepare"] = 1 if req_prepare else 0

    if active:
        # LKAS激活: 保持原厂格式，只改 Output 和 Active
        # cabana 旧版本分析:
        #   - LKAS_Config 始终=1 (ALARM)，不切换到 3 (ALARM_AND_LKA)
        #   - LKAS_State 始终=7，不切换到 2
        #   - ReqPrepare 大部分时间=0，只偶尔闪烁=1
        #   - Active=1 时直接输出 torque，EPS 立即响应
        values.update({
            "LKAS_Output": req_torque,
            "LKAS_Active": 1,
            # 保持原厂值: Config=1(ALARM), State=7
            # 车道线状态 (根据HUD控制更新)
            "LeftLaneState": 2 if hud_control.leftLaneVisible else 0,
            "RightLaneState": 2 if hud_control.rightLaneVisible else 0,
        })

    # 计算校验和
    data = packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(0xAF, data)

    return packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)


def create_fake_eps_feedback(packer, CP, CS, fake_torque: int, lkas_req_prepare: bool,
                             lkas_active: bool, enabled: bool):
    """
    生成EPS反馈欺骗报文 (ACC_EPS_STATE - 0x318)
    用于欺骗MPC，防止DTC故障码，保持AEB等安全功能正常工作

    参数:
        packer: CAN打包器
        CP: 车辆参数
        CS: 车辆状态
        fake_torque: 伪造的扭矩反馈值
        lkas_req_prepare: LKAS准备请求状态
        lkas_active: LKAS激活状态
        enabled: openpilot是否启用
    """
    values = {
        "LKAS_Prepared": 0,
        "CruiseActivated": 0,
        "TorqueFailed": 0,
        "SETME1_0x1": 1,
        "SteerWarning": 0,
        "SteerErrorCode": 0,
        "MainTorque": 0,
        "SETME3_0x1": 1,
        "ReportHandsNotOnSteeringWheel": 0,
        "SETME4_0x3": 3,
        "SteerDriverTorque": 0,  # 将由实际值覆盖
        "SETME5_0xFF": 0xF,
        "SETME6_0xFFF": 0xFFF,
    }

    # 保持驾驶员扭矩透传
    values["SteerDriverTorque"] = int(CS.steeringTorque) if hasattr(CS, 'steeringTorque') else 0

    if enabled:
        if lkas_active:
            # LKAS激活: 报告扭矩反馈
            values.update({
                "LKAS_Prepared": 0,
                "CruiseActivated": 1,
                "MainTorque": fake_torque,
            })
        elif lkas_req_prepare:
            # LKAS准备中
            values.update({
                "LKAS_Prepared": 1,
                "CruiseActivated": 0,
                "MainTorque": 0,
            })
        else:
            # LKAS关闭
            values.update({
                "LKAS_Prepared": 0,
                "CruiseActivated": 0,
                "MainTorque": 0,
            })

    # 计算校验和
    # ACC_EPS_STATE 的 COUNTER/CHECKSUM 已从 DBC 中移除（因为 RX 端不递增）
    # 但 TX 端仍需手动设置 checksum 到 byte 7
    msg = packer.make_can_msg("ACC_EPS_STATE", CanBus.CAM, values)
    dat = bytearray(msg[1])
    dat[7] = byd_checksum(0xAF, dat)
    return (msg[0], bytes(dat), msg[2])


def create_acc_cmd(packer, CP, CS, mrr_lead_dist: float, accel: float,
                   resume_from_standstill: bool, standstill_state: bool, long_active: bool,
                   counter: int = 0):
    """
    生成ACC控制指令报文 (ACC_CMD - 0x32E)
    用于openpilot纵向控制

    参数:
        packer: CAN打包器
        CP: 车辆参数
        CS: 车辆状态
        mrr_lead_dist: 前车距离 (米)
        accel: 目标加速度 (m/s²)
        resume_from_standstill: 是否从停车状态恢复
        standstill_state: 是否处于停车状态
        long_active: 纵向控制是否激活
    """
    # Jerk限制参数 (根据前车距离动态调整)
    K_jerk_xp = [10, 30, 50, 100]  # 距离点 (米)
    K_jerk_base_upper_fp = [2.0, 1.5, 1.0, 0.8]  # 上限jerk
    K_jerk_base_lower_fp = [3.0, 2.5, 2.0, 1.5]  # 下限jerk
    K_accel_jerk_upper = 0.3  # 加速度对jerk上限的影响系数
    K_accel_jerk_lower = 0.5  # 加速度对jerk下限的影响系数

    # 计算jerk限制
    jerk_base_upper = np.interp(mrr_lead_dist, K_jerk_xp, K_jerk_base_upper_fp)
    jerk_base_lower = np.interp(mrr_lead_dist, K_jerk_xp, K_jerk_base_lower_fp)

    if accel < 0:  # 减速时使用下限系数
        jerk_upper = jerk_base_upper
        jerk_lower = jerk_base_lower + accel * K_accel_jerk_lower
    else:  # 加速时使用上限系数
        jerk_upper = jerk_base_upper + accel * K_accel_jerk_upper
        jerk_lower = jerk_base_lower

    # 限制jerk范围
    jerk_upper = max(0.2, min(12.7, jerk_upper))
    jerk_lower = max(0.2, min(12.7, jerk_lower))

    values = {
        "AccelCmd": 0,
        "ComfortBandUpper": 0,
        "ComfortBandLower": 0,
        "JerkUpperLimit": 0,
        "SETME1_0x1": 1,
        "JerkLowerLimit": 0,
        "ResumeFromStandstill": 0,
        "StandstillState": 0,
        "BrakeBehaviour": 0,
        "AccReqNotStandstill": 0,
        "AccControlActive": 0,
        "AccOverrideOrStandstill": 0,
        "EspBehaviour": 0,
        "COUNTER": counter,
        "SETME2_0xF": 0xF,
    }

    if long_active:
        # 旧版本验证: 激活时只设 AccReqNotStandstill=1, AccControlActive=0
        # 车辆ECU根据AccReq来决定是否执行加速
        values.update({
            "AccelCmd": accel,
            "ComfortBandUpper": 0.05,
            "ComfortBandLower": 0.05,
            "ResumeFromStandstill": 1 if resume_from_standstill else 0,
            "StandstillState": 1 if standstill_state else 0,
            "AccControlActive": 0,
            "AccReqNotStandstill": 0 if standstill_state else 1,
        })

    # 计算校验和
    data = packer.make_can_msg("ACC_CMD", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(0xAF, data)

    return packer.make_can_msg("ACC_CMD", CanBus.PT, values)


def create_acc_hud(packer, CP, CS, set_speed: float, has_lead: bool,
                   set_distance: int, acc_state: int, enabled: bool,
                   counter: int = 0):
    """
    生成ACC HUD显示报文 (ACC_HUD_ADAS - 0x32D)
    用于更新仪表盘显示

    参数:
        packer: CAN打包器
        CP: 车辆参数
        CS: 车辆状态
        set_speed: 设定速度 (km/h)
        has_lead: 是否检测到前车
        set_distance: 跟车距离档位 (1-4)
        acc_state: ACC状态
        enabled: 是否启用
    """
    values = {
        "SetSpeed": set_speed,  # physical value in km/h, packer applies DBC scale
        "HasLead": 1 if has_lead else 0,
        "SetDistance": set_distance,
        "LeadingDistance": 0,
        "AEB": 0,
        "FCW": 0,
        "SETME1_0x1": 1,
        "AccState": acc_state,
        "AccOn1": 1 if enabled else 0,
        "CloseWarning": 0,
        "SETME2_0x1": 1,
        "Notify": 0,
        "Status": 4,  # old version idle = 4
        "SETME3_0xFFF": 0xFFF,
        "COUNTER": counter,
        "SETME4_0xF": 0xF,
    }

    # 计算校验和
    data = packer.make_can_msg("ACC_HUD_ADAS", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(0xAF, data)

    return packer.make_can_msg("ACC_HUD_ADAS", CanBus.PT, values)
