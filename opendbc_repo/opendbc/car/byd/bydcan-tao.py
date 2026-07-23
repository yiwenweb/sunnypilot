## ============================================================================
## bydcan-tao.py  —— 涛哥版 A 方案纯复刻 (供对照测试, 部署时改名为 bydcan.py)
## ----------------------------------------------------------------------------
## 与你现有 bydcan.py 的核心区别 (A 方案 = 100% 复刻涛哥, 不叠加你的改动):
##   1. create_steering_control: 【透传 LKAS_Config】(摄像头发什么转发什么, 不强制=3);
##      LKAS_State 跟随 MPC_State 走 (2/4), 不强制=7。
##   2. create_fake_318: 【主动伪造】(laks_active 时 Cru=1 + MainTorque=faketorque),
##      不是纯透传。counter 用自己的 eps_fake318_counter。
##   3. acc_cmd: counter 从摄像头 cam_msg 透传 (不自己编), 与 813/815 天然同步。
##   4. 【不含】create_acc_hud_adas / create_acc_aeb —— 涛哥靠摄像头原厂 813/815 透传,
##      故需配套的 byd-tao.h 放行摄像头 813/815 (只拦 814)。
##
## import 路径已适配你的 sunnypilot 2026 工程 (新版 opendbc)。
## ============================================================================
import numpy as np
from opendbc.car import structs
from opendbc.car.byd.values import CanBus, CarControllerParams

GearShifter = structs.CarState.GearShifter
VisualAlert = structs.CarControl.HUDControl.VisualAlert


def byd_checksum(byte_key, dat):
    first_bytes_sum = sum(byte >> 4 for byte in dat)
    second_bytes_sum = sum(byte & 0xF for byte in dat)
    remainder = second_bytes_sum >> 4
    second_bytes_sum += byte_key >> 4
    first_bytes_sum += byte_key & 0xF
    first_part = ((-first_bytes_sum + 0x9) & 0xF)
    second_part = ((-second_bytes_sum + 0x9) & 0xF)
    return (((first_part + (-remainder + 5)) << 4) + second_part) & 0xFF


# MPC -> Panda -> EPS  (790 ACC_MPC_STATE, 发到 Bus0/ESC)
# 涛哥原版: 透传摄像头的 LKAS_Config / LKAS_State 基线, active 时改 Output/Active/State/LaneState。
def create_steering_control(packer, CP, cam_msg: dict, req_torque, req_prepare, active, hud_control, counter):
    values = {s: cam_msg[s] for s in [
        "AutoFullBeamState",
        "LeftLaneState",
        "LKAS_Config",          # ← 透传 (不强制3), A 方案核心差异
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
    ]}

    values["ReqHandsOnSteeringWheel"] = 0
    values["LKAS_ReqPrepare"] = req_prepare
    values["Counter"] = counter

    if active:
        mpc_state = values["MPC_State"]  # 2: Cancelling lkas control
        values.update({
            "LKAS_Output": req_torque,
            "LKAS_Active": 1,
            "LKAS_State": 4 if (mpc_state == 2) else 2,   # ← 涛哥: 跟随 MPC_State, 不强制7
            "LeftLaneState":  3 if hud_control.leftLaneDepart  else int(hud_control.leftLaneVisible) + 1,
            "RightLaneState": 3 if hud_control.rightLaneDepart else int(hud_control.rightLaneVisible) + 1,
        })
    else:
        # Note: 涛哥注释 —— 这会禁用原厂 AEB 的"障碍物前转向"特性
        values.update({
            "LKAS_Output": 0,
            "LKAS_Active": 0,
        })

    data = packer.make_can_msg("ACC_MPC_STATE", CanBus.ESC, values)[1]
    values["CheckSum"] = byd_checksum(0xAF, data)
    return packer.make_can_msg("ACC_MPC_STATE", CanBus.ESC, values)


# op long control (814 ACC_CMD, 发到 Bus0/ESC)
# 涛哥原版: counter 从摄像头 cam_msg 透传 (在 copy 列表里), 与 813/815 天然同步。
def acc_cmd(packer, CP, cam_msg: dict, mrr_leaddist, accel, rfss, sss, longActive):
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
        "Counter",              # ← 透传摄像头 counter, 不自己编
        "SETME2_0xF",
    ]}

    jerk_base_upper = np.interp(mrr_leaddist, CarControllerParams.K_jerk_xp, CarControllerParams.K_jerk_base_upper_fp)
    jerk_base_lower = np.interp(mrr_leaddist, CarControllerParams.K_jerk_xp, CarControllerParams.K_jerk_base_lower_fp)

    if (accel < 0):  # use lower factor
        jerk_upper = jerk_base_upper
        jerk_lower = jerk_base_lower + accel * CarControllerParams.K_accel_jerk_lower
    else:
        jerk_upper = jerk_base_upper + accel * CarControllerParams.K_accel_jerk_upper
        jerk_lower = jerk_base_lower

    if longActive:
        values.update({
            "AccelCmd": accel,
            "ComfortBandUpper": 0.05 if mrr_leaddist > 50 else 0.10,
            "ComfortBandLower": 0.05 if mrr_leaddist > 50 else 0.10,
            "JerkUpperLimit": jerk_upper,
            "JerkLowerLimit": jerk_lower,
            "ResumeFromStandstill": rfss,
            "StandstillState": sss,
        })

    data = packer.make_can_msg("ACC_CMD", CanBus.ESC, values)[1]
    values["CheckSum"] = byd_checksum(0xAF, data)
    return packer.make_can_msg("ACC_CMD", CanBus.ESC, values)


# send fake torque feedback from eps to trick MPC, preventing DTC, so that safety features such as AEB still working
# 涛哥原版 主动伪造: 用摄像头自己的请求状态 (laks_active/reqprepare) 去伪造摄像头期望的 EPS 应答。
#   laks_active   -> Prepared=0, CruiseActivated=1, MainTorque=faketorque(=摄像头自己的LKAS_Output)
#   laks_reqprepare-> Prepared=1, CruiseActivated=0, MainTorque=0
#   else          -> Prepared=0, CruiseActivated=0, MainTorque=0
# 发到 Bus2/MPC, 摄像头永远认为"我要的扭矩 EPS 给到了" -> 不判冲突/不撤LKAS/不DTC -> 保住AEB。
def create_fake_318(packer, CP, esc_msg: dict, faketorque, laks_reqprepare, laks_active, enabled, counter):
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
    ]}

    values["ReportHandsNotOnSteeringWheel"] = 0
    values["Counter"] = counter    # ← 涛哥: 用自己的 eps_fake318_counter

    if enabled:
        if laks_active:
            values.update({
                "LKAS_Prepared": 0,
                "CruiseActivated": 1,
                "MainTorque": faketorque,
            })
        elif laks_reqprepare:
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

    data = packer.make_can_msg("ACC_EPS_STATE", CanBus.MPC, values)[1]
    values["CheckSum"] = byd_checksum(0xAF, data)
    return packer.make_can_msg("ACC_EPS_STATE", CanBus.MPC, values)
