import copy
import numpy as np

from opendbc.can import CANDefine, CANParser

from opendbc.car.common.conversions import Conversions as CV
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.interfaces import CarStateBase
from opendbc.car.byd.values import DBC, CanBus, LKASConfig, CarControllerParams

import os
BYD_RADAR = os.getenv("BYD_RADAR") is not None

ButtonType = structs.CarState.ButtonEvent.Type


class CarState(CarStateBase):
    def __init__(self, CP, CP_SP):
        super().__init__(CP, CP_SP)

        can_define = CANDefine(DBC[CP.carFingerprint][Bus.pt])
        self.shifter_values = can_define.dv["DRIVE_STATE"]["Gear"]

        self.speed_kph = 0

        self.mpc_lkas_config = 0

        self.acc_hud_adas_counter = 0
        self.acc_mpc_state_counter = 0
        self.acc_cmd_counter = 0

        self.eps_warning = False
        self.torque_failed_counter = 0

        self.acc_active_last = False
        self.low_speed_alert = False
        self.lkas_allowed_speed = False

        self.lkas_prepared = False
        self.eps_cruise_activated = False
        # 机制①: EPS 单方面切断横向控制的检测/报警状态
        self.eps_cruise_activated_last = False
        self.eps_cut_alert_frames = 0
        self.acc_state = 0
        self.adas_set_dist = 0

        self.mpc_laks_output = 0
        self.mpc_laks_active = False
        self.mpc_laks_reqprepare = False

        self.cam_lkas = {}
        self.cam_acc = {}
        self.cam_adas = {}
        self.esc_eps = {}

        self.setTimeDelay = 100

        self.mrr_leading_dist = 0

        self.btn_acc_cancel = 0
        self.btn_acc_set_reset = 0
        self.btn_acc_dist_inc = 0
        self.btn_acc_dist_dec = 0

        self.steeringRateDegAbs = 0

    def update(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
        cp = can_parsers[Bus.pt]
        cp_cam = can_parsers[Bus.cam]

        ret = structs.CarState()
        ret_sp = structs.CarStateSP()

        # LKAS_Prepared (bit0) is the working handshake signal — confirmed on-vehicle:
        # with STEER_MAX=300, lateral controls the wheel when using bit0; bit1 does not work.
        self.lkas_prepared = bool(cp.vl["ACC_EPS_STATE"]["LKAS_Prepared"])
        # EPS CruiseActivated (bit1): 门总接管序列里, Act=1 后必须等此位=1 才开始发扭矩。
        # 在 Cru=0 时发非零扭矩会被 panda 拦截(steer_req=Active&&CruiseActivated), EPS 收到
        # Active 却收不到扭矩 -> 电机 MainTorque=0 -> 0.7s 后 TorqueFailed 锁死 (LOCK1)。
        self.eps_cruise_activated = bool(cp.vl["ACC_EPS_STATE"]["CruiseActivated"])

        self.mpc_lkas_config = int(cp_cam.vl["ACC_MPC_STATE"]["LKAS_Config"])
        lkas_config_isAccOn = (self.mpc_lkas_config != LKASConfig.DISABLE)
        lkas_isMainSwOn = bool(cp.vl["PCM_BUTTONS"]["BTN_TOGGLE_ACC_OnOff"])

        lkas_hud_AccOn1 = bool(cp_cam.vl["ACC_HUD_ADAS"]["AccOn1"])
        self.acc_state = cp_cam.vl["ACC_HUD_ADAS"]["AccState"]
        self.adas_set_dist = cp_cam.vl["ACC_HUD_ADAS"]["SetDistance"]

        prev_btn_acc_cancel = self.btn_acc_cancel
        prev_btn_acc_set_reset = self.btn_acc_set_reset
        prev_btn_acc_dist_inc = self.btn_acc_dist_inc
        prev_btn_acc_dist_dec = self.btn_acc_dist_dec

        self.btn_acc_cancel = cp.vl["PCM_BUTTONS"]["BTN_AccCancel"]
        self.btn_acc_set_reset = cp.vl["PCM_BUTTONS"]["BTN_AccUpDown_Cmd"]
        self.btn_acc_dist_inc = cp.vl["PCM_BUTTONS"]["BTN_AccDistanceIncrease"]
        self.btn_acc_dist_dec = cp.vl["PCM_BUTTONS"]["BTN_AccDistanceDecrease"]

        # use dash speedo as speed reference
        speed_raw = int(cp.vl["CARSPEED"]["CarDisplaySpeed"])
        speed_raw_kph = speed_raw * CarControllerParams.K_DASHSPEED
        correct_factor = np.interp(speed_raw_kph, [30, 60, 90, 120], [1., 1., 1., 1.])
        self.speed_kph = speed_raw_kph * correct_factor

        ret.vEgoRaw = float(self.speed_kph * CV.KPH_TO_MS)
        ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)

        ret.yawRate = cp.vl["YAW_RATE"]["YawRate"] - cp.vl["YAW_RATE"]["YawRateOffset"]

        ret.standstill = (speed_raw == 0)

        if self.CP.minSteerSpeed > 0:
            if self.speed_kph > 0.5:
                self.lkas_allowed_speed = True
            elif self.speed_kph < 0.1:
                self.lkas_allowed_speed = False
        else:
            self.lkas_allowed_speed = True

        can_gear = int(cp.vl["DRIVE_STATE"]["Gear"])
        ret.gearShifter = self.parse_gear_shifter(self.shifter_values.get(can_gear, None))

        ret.genericToggle = bool(cp.vl["STALKS"]["HeadLight"])
        if self.CP.enableBsm:
            ret.leftBlindspot = bool(cp.vl["BSD_RADAR"]["LEFT_APPROACH"])
            ret.rightBlindspot = bool(cp.vl["BSD_RADAR"]["RIGHT_APPROACH"])

        ret.leftBlinker = bool(cp.vl["STALKS"]["LeftIndicator"])
        ret.rightBlinker = bool(cp.vl["STALKS"]["RightIndicator"])

        ret.steeringAngleOffsetDeg = 0
        ret.steeringAngleDeg = cp.vl["EPS"]["SteeringAngle"]

        self.steeringRateDegAbs = cp.vl["EPS"]["SteeringAngleRate"]
        ret.steeringRateDeg = self.steeringRateDegAbs

        ret.steeringTorque = cp.vl["ACC_EPS_STATE"]["SteerDriverTorque"]
        ret.steeringTorqueEps = cp.vl["ACC_EPS_STATE"]["MainTorque"]
        self.eps_warning = bool(cp.vl["ACC_EPS_STATE"]["SteerWarning"])
        self.eps_state_counter = int(cp.vl["ACC_EPS_STATE"]["Counter"])

        # 驾驶员接管判定阈值 (steeringPressed): 校准到 EPS 的 hands-on(握持)检测水平, 使 C3 边框
        # 蓝->灰 与 "达到 EPS 认可的握持力" 对齐, 让边框成为 EPS 握持状态的实时指示灯。
        # 单位说明: steeringTorque = 318.SteerDriverTorque 原始CAN计数 (12-bit signed, scale=1),
        #   不是 Nm。按 EPS 扭矩传感器典型满量程 ±2047≈±10Nm 估算, 1计数≈0.005Nm。
        #   实测数据验证该系数合理: 门总 max=879≈4.3Nm(用力打方向), 均值75≈0.37Nm(搭手)。
        # 历史: 旧值 59(≈0.29Nm) 是上游默认值, 偏"override/主动干预"级, 高于 EPS 的 hands-on 水平,
        #   导致轻搭手/配重块能被 EPS 认可却不足以让 C3 变灰。现下调到 30(≈0.15Nm), 贴近 EPS hands-on。
        # 噪声权衡: 车停/脱手时静态噪声峰值 ±57、均值14.5, 阈值30 落在噪声带内。故把滤波从 5 帧
        #   加长到 12 帧(~0.24s): 随机噪声难连续12帧超30, 真握持则持续超30 -> 既灵敏又不误报。
        # TODO(实车标定): developer UI 已加 DRV TQ 实时显示。挂配重块读出其稳定原始值 X, 并确认车辆
        #   仪表不报离手, 则将阈值定为略低于 X (X-5) 即可精确对齐 EPS。当前 30 为基于估算的初值。
        ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > 30, 12)

        ret.parkingBrake = (cp.vl["EPB"]["EPB_ActiveFlag"] == 1)

        brake = int(cp.vl["PEDAL"]["BrakePedal"])
        ret.brakePressed = (brake != 0)

        ret.seatbeltUnlatched = (cp.vl["BELT"]["SeatBeat"] != 2)

        ret.doorOpen = any([cp.vl["BCM"]["FrontLeftDoor"], cp.vl["BCM"]["FrontRightDoor"],
                            cp.vl["BCM"]["RearLeftDoor"], cp.vl["BCM"]["RearRightDoor"]])

        gas = int(cp.vl["PEDAL"]["AcceleratorPedal"])
        ret.gasPressed = (gas != 0)

        # FIXED: removed lkas_isMainSwOn (944 momentary button) - use only persistent states from 813
        ret.cruiseState.available = lkas_config_isAccOn and lkas_hud_AccOn1
        # enabled only when ACC truly engaged (3=ACC_ACTIVE, 5=FORCE_ACCEL).
        # Excludes 1=standby: with pcmCruise, treating standby as enabled would fire
        # pcmEnable (green/longitudinal) the moment ACC switch is pressed, skipping the
        # blue lateral-only state. Lateral (MADS) uses cruiseState.available, not enabled.
        ret.cruiseState.enabled = self.acc_state in (3, 5)
        ret.cruiseState.standstill = ret.standstill
        ret.cruiseState.speed = cp_cam.vl["ACC_HUD_ADAS"]["SetSpeed"] * CV.KPH_TO_MS

        # Note: some firmware versions have SteerWarning always asserted, so we ignore it for now
        # ret.steerFaultTemporary = bool((self.acc_state == 7) or self.eps_warning)

        # 机制①: EPS 单方面切断横向控制的报警 (复刻门总: EPS 撤销授权时 C3 立即声光提醒)。
        # 判据: EPS CruiseActivated 1->0, 且此刻 ACC 仍处于激活态(3/5) => 不是驾驶员正常退出
        # (取证: 正常退出时掉线都发生在 ACC 已退出/停车, op 侧先松手; 而"过弯中 EPS 强行切断"
        #  会在 ACC 仍激活时把 Cru 拉低, 即本判据)。触发后保持 ~1s(50帧) 让报警可感知,
        # Cru 恢复或 ACC 退出即结束。用 steerFaultTemporary, openpilot 会自动出声光警告。
        acc_engaged = self.acc_state in (3, 5)
        eps_cut = (self.eps_cruise_activated_last and not self.eps_cruise_activated and acc_engaged)
        if eps_cut:
            self.eps_cut_alert_frames = 50
        elif self.eps_cut_alert_frames > 0 and acc_engaged and not self.eps_cruise_activated:
            self.eps_cut_alert_frames -= 1
        else:
            self.eps_cut_alert_frames = 0
        self.eps_cruise_activated_last = self.eps_cruise_activated

        ret.steerFaultTemporary = bool((self.acc_state == 7) or (self.eps_cut_alert_frames > 0))

        self.acc_active_last = ret.cruiseState.enabled

        self.mpc_laks_output = cp_cam.vl["ACC_MPC_STATE"]["LKAS_Output"]
        self.mpc_laks_reqprepare = cp_cam.vl["ACC_MPC_STATE"]["LKAS_ReqPrepare"] != 0
        self.mpc_laks_active = cp_cam.vl["ACC_MPC_STATE"]["LKAS_Active"] != 0

        self.acc_hud_adas_counter = cp_cam.vl["ACC_HUD_ADAS"]["Counter"]
        self.acc_mpc_state_counter = cp_cam.vl["ACC_MPC_STATE"]["Counter"]
        self.acc_cmd_counter = cp_cam.vl["ACC_CMD"]["Counter"]

        self.cam_lkas = copy.copy(cp_cam.vl["ACC_MPC_STATE"])
        self.cam_adas = copy.copy(cp_cam.vl["ACC_HUD_ADAS"])
        self.cam_acc = copy.copy(cp_cam.vl["ACC_CMD"])
        self.esc_eps = copy.copy(cp.vl["ACC_EPS_STATE"])

        if BYD_RADAR:
            mrr_id = int(cp_cam.vl["RADAR_MRR"]["TargetID"])
            if mrr_id == 2:
                if bool(cp_cam.vl["RADAR_MRR"]["IsValid"]):
                    self.mrr_leading_dist = int(cp_cam.vl["RADAR_MRR"]["LongDist"])
                else:
                    self.mrr_leading_dist = 199

        # TorqueFailed: EPS rejects control and requires vehicle restart to recover.
        # Confirmed: byte0=0xFC (bit2=1) when EPS locks up; bit0 never goes 1 in that state.
        self.torque_failed_counter = 0
        ret.steerFaultPermanent = bool(cp.vl["ACC_EPS_STATE"]["TorqueFailed"])

        ret.buttonEvents = [
            *create_button_events(self.btn_acc_cancel, prev_btn_acc_cancel, {1: ButtonType.cancel}),
            *create_button_events(self.btn_acc_set_reset, prev_btn_acc_set_reset, {1: ButtonType.decelCruise, 3: ButtonType.accelCruise}),
            *create_button_events(self.btn_acc_dist_inc, prev_btn_acc_dist_inc, {1: ButtonType.gapAdjustCruise}),
            *create_button_events(self.btn_acc_dist_dec, prev_btn_acc_dist_dec, {1: ButtonType.gapAdjustCruise}),
        ]

        return ret, ret_sp


    @staticmethod
    def get_can_parsers(CP, CP_SP):
        pt_messages = [
            ("EPS", 100),
            ("CARSPEED", 50),
            ("PEDAL", 50),
            ("EPB", 1),
            ("ACC_EPS_STATE", 50),
            ("DRIVE_STATE", 50),
            ("STALKS", 1),
            ("BCM", 1),
            ("PCM_BUTTONS", 20),
            ("DATETIME", 2),
            ("YAW_RATE", 50),
            ("BELT", 20),
        ]

        if CP.enableBsm:
            pt_messages.append(("BSD_RADAR", 20))

        cam_messages = [
            ("ACC_HUD_ADAS", 50),
            ("ACC_CMD", 50),
            ("ACC_MPC_STATE", 50),
        ]
        if BYD_RADAR:
            cam_messages.append(("RADAR_MRR", 60))

        return {
            Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], pt_messages, CanBus.ESC),
            Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], cam_messages, CanBus.MPC),
        }
