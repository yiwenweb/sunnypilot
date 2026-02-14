"""
BYD CAN message generation module.

This module provides functions to create CAN messages for BYD vehicles,
including steering control, ACC commands, and HUD display messages.

=== （五）重要安全提醒 ===
1. 仅辅助，不可脱手，随时接管
2. 弯道、雨雪、标线模糊、施工路段慎用/关闭
3. 不识别行人、非机动车、静止障碍物
4. 升级后功能以4S店开通版本为准
"""

import numpy as np

from opendbc.car.byd.values import CanBus


def byd_checksum(dat: bytes) -> int:
    """
    计算BYD唐DM 2018款原厂校验和
    原厂算法：sum(all 8 bytes) & 0xFF == 0xFF
    即 CHECKSUM = (0xFF - sum(前7字节)) & 0xFF

    通过实车嗅探验证（sniff_mpc_frames.py, 39.5秒采样）：
      790/792/813/814/815 全部符合此算法

    参数:
        dat: CAN报文原始字节数据（长度≥7）
    返回:
        8位校验和值（0-255）
    """
    return (0xFF - sum(dat[:7])) & 0xFF


def create_steering_control(packer, CP, apply_torque: int, req_prepare: bool,
                            active: bool, brake_pressed: bool, hud_control, counter: int):
    """
    生成转向控制报文 (ACC_MPC_STATE - 0x316 / 790)

    参数:
        packer: CAN打包器
        CP: 车辆参数
        apply_torque: 请求的转向扭矩（原始值，11-bit signed [-1024, 1023]）
        req_prepare: 是否请求准备状态
        active: LKAS是否激活
        brake_pressed: 刹车是否踩下（制动优先级）
        hud_control: HUD控制信息（车道线可见性）
        counter: 报文计数器 (0-15)
    """
    values = {
        "AutoFullBeamState": 1,           # 原厂空闲值=1 (实测)
        "LeftLaneState": 0,
        "LKAS_Config": 1,                 # 原厂空闲值=1 (实测)
        "SETME2_0x1": 1,
        "ReqHandsOnSteeringWheel": 0,
        "MPC_State": 0,
        "AutoFullBeam_OnOff": 1,
        "LKAS_Output": 0,
        "LKAS_ReqPrepare": 0,
        "LKAS_Active": 0,
        "SETME3_0x0": 0,
        "TrafficSignRecognition_OnOff": 1, # 原厂空闲值=1 (实测)
        "SETME4_0x0": 0,
        "SETME5_0x1": 1,
        "RightLaneState": 0,
        "LKAS_State": 7,
        "TrafficSignRecognition_Result": 0,
        "LKAS_AlarmType": 0,
        "SETME7_0x3": 3,
        "COUNTER": counter,
        "CHECKSUM": 0,
    }

    values["LKAS_ReqPrepare"] = 1 if req_prepare else 0

    # 制动优先级：踩刹车立即关闭LKAS
    if brake_pressed:
        active = False
        values["LKAS_Active"] = 0
        values["LKAS_Output"] = 0
    elif active:
        # LKAS_Output 是 11-bit signed，DBC scale=1，原始值直接映射到EPS扭矩
        # apply_torque 已经被 apply_driver_steer_torque_limits 限制在 ±STEER_MAX(1023)
        values.update({
            "LKAS_Output": apply_torque,
            "LKAS_Active": 1,
            "LeftLaneState": 2 if hud_control.leftLaneVisible else 0,
            "RightLaneState": 2 if hud_control.rightLaneVisible else 0,
        })

    data = packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(data)

    return packer.make_can_msg("ACC_MPC_STATE", CanBus.PT, values)


def create_fake_eps_feedback(packer, fake_torque: int, driver_torque: int,
                             lkas_req_prepare: bool, lkas_active: bool, enabled: bool,
                             counter: int = 0):
    """
    生成EPS反馈欺骗报文 (ACC_EPS_STATE - 0x318 / 792)
    发送到Bus 2，欺骗原厂MPC，防止DTC故障码，保持AEB等安全功能正常工作

    原厂 EPS 实测数据 (sniff_mpc_frames.py, 39.5秒):
      fc 00 f0 XX ff ff Cx xx
      byte[0]=0xFC: LKAS_Prepared=0, CruiseActivated=0, TorqueFailed=1,
                    SETME1_0x1=1, SteerWarning=1, SteerErrorCode=7
      byte[2]=0xF0: MainTorque=0, SETME3_0x1=1, ReportHandsNotOnSteeringWheel=1, SETME4_0x3=3
      byte[4]=0xFF: SETME5_0xFF=0xF
      byte[5]=0xFF: SETME6_0xFFF=0xFFF
      byte[6]: 高4位=COUNTER(0-F), 低4位=0xF (SETME)
      byte[7]: CHECKSUM (sum(all 8 bytes) & 0xFF == 0xFF)

    关键发现:
      - TorqueFailed=1, SteerWarning=1, SteerErrorCode=7 是 EPS 正常状态
      - 如果发送 0 会导致 MPC 检测到异常
      - 792 也有 counter 和 checksum，但 DBC 未定义这两个信号
      - 必须手动填充 byte[6] 和 byte[7]

    参数:
        packer: CAN打包器
        fake_torque: 伪造的EPS扭矩反馈值
        driver_torque: 驾驶员方向盘扭矩（透传给MPC）
        lkas_req_prepare: LKAS准备请求状态
        lkas_active: LKAS激活状态
        enabled: openpilot是否启用
        counter: 报文计数器 (0-15)
    """
    # 严格匹配原厂 EPS 的 792 帧格式
    values = {
        "LKAS_Prepared": 0,
        "CruiseActivated": 0,
        "TorqueFailed": 1,             # 原厂 EPS 正常状态 = 1（非故障）
        "SETME1_0x1": 1,
        "SteerWarning": 1,             # 原厂 EPS 正常状态 = 1（非故障）
        "SteerErrorCode": 7,           # 原厂 EPS 正常状态 = 7
        "MainTorque": 0,
        "SETME3_0x1": 1,
        "ReportHandsNotOnSteeringWheel": 0,
        "SETME4_0x3": 3,
        "SteerDriverTorque": int(driver_torque),
        "SETME5_0xFF": 0xF,
        "SETME6_0xFFF": 0xFFF,
    }

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

    msg = packer.make_can_msg("ACC_EPS_STATE", CanBus.CAM, values)
    dat = bytearray(msg[1])
    # 手动填充 counter 和 checksum（DBC 未定义这两个信号）
    # 原厂格式: byte[6] = (counter << 4) | 0xF, byte[7] = checksum
    dat[6] = ((counter & 0xF) << 4) | 0xF
    dat[7] = byd_checksum(dat)
    return (msg[0], bytes(dat), msg[2])


def create_acc_cmd(packer, CP, CS, mrr_lead_dist: float, accel: float,
                   resume_from_standstill: bool, standstill_state: bool, long_active: bool,
                   counter: int = 0):
    """
    生成ACC控制指令报文 (ACC_CMD - 0x32E / 814)
    用于openpilot纵向控制（加速/减速/跟车）
    
    核心修正：
    1. 限制AccelCmd在原厂范围(-5 ~ 7.75 m/s²)，避免ECU忽略指令
    2. 修复校验和计算（使用原厂补码算法）
    3. 优化Jerk限制参数（贴近原厂默认值）
    
    参数:
        packer: CAN打包器
        CP: 车辆参数
        CS: 车辆状态
        mrr_lead_dist: 前车距离 (米)
        accel: 目标加速度 (m/s²)
        resume_from_standstill: 是否从停车状态恢复（适配0km/h激活）
        standstill_state: 是否处于停车状态
        long_active: 纵向控制是否激活
    """
    # Jerk限制参数（修正为原厂默认值，提升兼容性）
    K_jerk_xp = [10, 30, 50, 100]  # 距离点 (米)
    K_jerk_base_upper_fp = [2.0, 1.5, 1.0, 0.8]  # 上限jerk（原厂默认≤12.7）
    K_jerk_base_lower_fp = [3.0, 2.5, 2.0, 1.5]  # 下限jerk（原厂默认≥-16）
    K_accel_jerk_upper = 0.3  # 加速度对jerk上限的影响系数
    K_accel_jerk_lower = 0.5  # 加速度对jerk下限的影响系数

    # 计算jerk限制（基于前车距离动态调整）
    jerk_base_upper = np.interp(mrr_lead_dist, K_jerk_xp, K_jerk_base_upper_fp)
    jerk_base_lower = np.interp(mrr_lead_dist, K_jerk_xp, K_jerk_base_lower_fp)

    if accel < 0:  # 减速时使用下限系数
        jerk_upper = jerk_base_upper
        jerk_lower = jerk_base_lower + accel * K_accel_jerk_lower
    else:  # 加速时使用上限系数
        jerk_upper = jerk_base_upper + accel * K_accel_jerk_upper
        jerk_lower = jerk_base_lower

    # 限制jerk在原厂允许范围
    jerk_upper = max(0.2, min(12.7, jerk_upper))  # 原厂上限12.7
    jerk_lower = max(-16.0, min(12.7, jerk_lower)) # 原厂下限-16

    # 原厂ACC_CMD基准值
    # 注意: AccelCmd 的 DBC 定义是 scale=0.05, offset=-5
    # 所以物理值 0 m/s² = raw 100, 物理值 -5 m/s² = raw 0
    # 空闲时必须发送 AccelCmd=0 (物理值，packer 会自动转换为 raw=100)
    # ComfortBand 同理: 物理值 0 = raw 100
    values = {
        "AccelCmd": 0,                  # 物理值 0 m/s² (packer 转为 raw=100)
        "ComfortBandUpper": 0,          # 物理值 0 m/s²
        "ComfortBandLower": 0,          # 物理值 0 m/s²
        "JerkUpperLimit": 0,
        "SETME1_0x1": 1,
        "JerkLowerLimit": 0,            # 物理值 0-16=-16 m/s³ (packer 转为 raw=80)
        "ResumeFromStandstill": 0,
        "StandstillState": 0,
        "BrakeBehaviour": 0,
        "AccReqNotStandstill": 0,
        "AccControlActive": 0,
        "AccOverrideOrStandstill": 0,
        "EspBehaviour": 0,
        "COUNTER": counter,
        "SETME2_0xF": 0xF,
        "CHECKSUM": 0,
    }

    if long_active:
        # 核心修正：限制加速度指令在原厂范围(-5 ~ 7.75 m/s²)
        limited_accel = max(-5.0, min(7.75, accel))
        values.update({
            "AccelCmd": limited_accel,               # 限制后加速度
            "ComfortBandUpper": 0.05,
            "ComfortBandLower": 0.05,
            "JerkUpperLimit": jerk_upper,
            "JerkLowerLimit": jerk_lower,
            "ResumeFromStandstill": 1 if resume_from_standstill else 0,
            "StandstillState": 1 if standstill_state else 0,
            "AccControlActive": 0,                   # 原厂激活时固定为0
            "AccReqNotStandstill": 0 if standstill_state else 1,
        })

    # 计算原厂补码校验和
    data = packer.make_can_msg("ACC_CMD", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(data)

    return packer.make_can_msg("ACC_CMD", CanBus.PT, values)


def create_acc_hud(packer, CP, CS, set_speed: float, has_lead: bool,
                   set_distance: int, acc_state: int, enabled: bool,
                   counter: int = 0):
    """
    生成ACC HUD显示报文 (ACC_HUD_ADAS - 0x32D / 813)
    用于更新仪表盘ACC状态显示（适配0km/h激活）

    原厂 MPC 实测数据 (sniff_mpc_frames.py, 39.5秒):
      空闲: 00 00 04 01 f4 ff Fx xx → AccState=0, AccOn1=0, Status=4, Notify=0
      ACC激活: 00 00 7c 4d f7 ff Fx xx → AccState=7, AccOn1=0, Status=7, Notify=38

    关键发现:
      - AccOn1 始终为 0（即使 ACC 激活）
      - AccState=7 表示 ACC 激活（DBC VAL_ 标注为 ERROR 是错误的）
      - Status=7 表示 ACC 激活
      - Notify=38 表示 ACC 激活通知

    参数:
        packer: CAN打包器
        CP: 车辆参数
        CS: 车辆状态
        set_speed: 设定速度 (km/h，支持0km/h)
        has_lead: 是否检测到前车
        set_distance: 跟车距离档位 (1-4)
        acc_state: ACC状态（由调用方传入，但会被覆盖为原厂值）
        enabled: 是否启用
        counter: 报文计数器 (0-15)
    """
    # 严格匹配原厂 MPC 帧格式
    # 空闲: AccState=0, AccOn1=0, Status=4, Notify=0
    # 激活: AccState=7, AccOn1=0, Status=7, Notify=38
    values = {
        "SetSpeed": set_speed if enabled else 0,
        "HasLead": 1 if has_lead else 0,
        "SetDistance": max(1, min(4, set_distance)),
        "LeadingDistance": 0,
        "AEB": 0,
        "FCW": 0,
        "SETME1_0x1": 1,
        "AccState": 0,                 # 默认空闲
        "AccOn1": 0,                   # 原厂始终为 0
        "CloseWarning": 0,
        "SETME2_0x1": 1,
        "Notify": 0,                   # 默认无通知
        "Status": 4,                   # 默认空闲
        "SETME3_0xFFF": 0xFFF,
        "COUNTER": counter,
        "SETME4_0xF": 0xF,
        "CHECKSUM": 0,
    }

    if enabled:
        # 匹配原厂 ACC 激活状态
        values.update({
            "AccState": 7,              # 原厂 ACC 激活 = 7（非 DBC 标注的 ERROR）
            "Status": 7,                # 原厂 ACC 激活 = 7
            "Notify": 38,               # 原厂 ACC 激活通知
        })

    data = packer.make_can_msg("ACC_HUD_ADAS", CanBus.PT, values)[1]
    values["CHECKSUM"] = byd_checksum(data)

    return packer.make_can_msg("ACC_HUD_ADAS", CanBus.PT, values)