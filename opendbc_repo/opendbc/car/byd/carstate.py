"""
BYD CarState - Vehicle state parsing implementation.

核心改动 (参考涛哥 carrotpilot):
1. 增加 Bus 2 (MPC) 帧解析 — 读取原厂 MPC 的 790/813/814 信号值
2. 缓存原厂帧数据 (cam_lkas, cam_acc, esc_eps) 供 carcontroller 透传
3. 读取原厂 counter 值供 carcontroller 接续
4. 读取 EPS 的 LKAS_Prepared 状态供 carcontroller 判断准备完成
"""

import copy
from enum import StrEnum

from opendbc.can import CANParser
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarStateBase
from opendbc.car.byd.values import DBC, STEER_THRESHOLD, CanBus

ButtonType = structs.CarState.ButtonEvent.Type
GearShifter = structs.CarState.GearShifter

CRUISE_BUTTONS_DICT = {
    1: ButtonType.decelCruise,
    3: ButtonType.accelCruise,
}

ACTIVATE_BUTTON_DICT = {
    1: ButtonType.setCruise,
}


class CarState(CarStateBase):
    def __init__(self, CP, CP_SP):
        super().__init__(CP, CP_SP)
        self.frame = 0

        # Button states
        self.cruise_buttons_prev = 0
        self.main_on_prev = False
        self.main_on = False
        self.cancel_button_prev = 0
        self.distance_decrease_prev = 0
        self.distance_increase_prev = 0
        self.activate_button_prev = 0

        # LKAS status from EPS 792
        self.lkas_active = False
        self.lkas_prepared = False

        # Steering state
        self.steer_torque_driver = 0
        self.steer_torque_motor = 0

        # Dynamic signals
        self.ax_sensor = 0.0

        # === 原厂帧缓存 (供 carcontroller 透传) ===
        # Bus 2 上 MPC 原厂帧的信号值字典
        self.cam_lkas = {}    # ACC_MPC_STATE (790) 原厂信号
        self.cam_acc = {}     # ACC_CMD (814) 原厂信号
        self.cam_adas = {}    # ACC_HUD_ADAS (813) 原厂信号
        # Bus 0 上 EPS 真实帧的信号值字典
        self.esc_eps = {}     # ACC_EPS_STATE (792) 真实信号

        # === 原厂 counter 值 (供 carcontroller 接续) ===
        self.acc_mpc_state_counter = 0   # 790 counter
        self.acc_cmd_counter = 0         # 814 counter
        self.acc_hud_adas_counter = 0    # 813 counter
        self.eps_state_counter = 0       # 792 counter

        # === MPC 原厂 LKAS 状态 (供 fake 792 透传) ===
        self.mpc_laks_output = 0
        self.mpc_laks_active = False
        self.mpc_laks_reqprepare = False

    def update(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
        cp = can_parsers[Bus.pt]       # Bus 0 - Powertrain / ESC
        cp_cam = can_parsers[Bus.cam]  # Bus 2 - MPC 原厂帧

        ret = structs.CarState()
        ret_sp = structs.CarStateSP()

        self.frame += 1

        # ===================== 车速解析 =====================
        v_ego_kmh = cp.vl["CARSPEED"]["CarDisplaySpeed"]
        ret.vEgoRaw = v_ego_kmh * CV.KPH_TO_MS
        ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
        ret.standstill = ret.vEgo < 0.1
        ret.vEgoCluster = ret.vEgoRaw

        # ===================== 方向盘角度/速率 =====================
        ret.steeringAngleDeg = cp.vl["EPS"]["SteeringAngle"]
        ret.steeringRateDeg = cp.vl["EPS"]["SteeringAngleRate"]

        # ===================== 方向盘扭矩 =====================
        self.steer_torque_driver = cp.vl["ACC_EPS_STATE"]["SteerDriverTorque"]
        self.steer_torque_motor = cp.vl["ACC_EPS_STATE"]["MainTorque"]
        ret.steeringTorque = self.steer_torque_driver
        ret.steeringTorqueEps = self.steer_torque_motor
        ret.steeringPressed = self.update_steering_pressed(abs(self.steer_torque_driver) > STEER_THRESHOLD, 50)

        # ===================== 转向故障 =====================
        ret.steerFaultTemporary = False
        ret.steerFaultPermanent = False

        # ===================== 档位 =====================
        gear = cp.vl["DRIVE_STATE"]["Gear"]
        ret.gearShifter = self._parse_gear(gear)

        # ===================== 踏板 =====================
        accelerator_pedal = cp.vl["PEDAL"]["AcceleratorPedal"]
        ret.gasPressed = accelerator_pedal > 0.01
        ret.brakePressed = cp.vl["DRIVE_STATE"]["BrakePressed"] == 1

        # ===================== 转向灯/车门/安全带 =====================
        ret.leftBlinker, ret.rightBlinker = self.update_blinker_from_stalk(
            100, cp.vl["STALKS"]["LeftIndicator"] == 1, cp.vl["STALKS"]["RightIndicator"] == 1)
        ret.doorOpen = any([
            cp.vl["BCM"]["FrontLeftDoor"], cp.vl["BCM"]["FrontRightDoor"],
            cp.vl["BCM"]["RearLeftDoor"], cp.vl["BCM"]["RearRightDoor"],
            cp.vl["BCM"]["BootDoor"],
        ])
        ret.seatbeltUnlatched = cp.vl["BCM"]["DriverSeatBeltFasten"] == 0

        # ===================== 巡航控制 =====================
        main_on = cp.vl["PCM_BUTTONS"]["BTN_TOGGLE_ACC_OnOff"] == 1
        ret.cruiseState.available = main_on
        ret.cruiseState.enabled = False
        ret.cruiseState.standstill = ret.standstill
        ret.cruiseState.speed = 0
        ret.buttonEvents = self._parse_button_events(cp, main_on)

        # ===================== EPS 792 状态 (Bus 0) =====================
        self.lkas_prepared = cp.vl["ACC_EPS_STATE"]["LKAS_Prepared"] == 1
        self.eps_state_counter = int(cp.vl["ACC_EPS_STATE"]["COUNTER_792"])

        # ===================== 横摆率/加速度 =====================
        ret.yawRate = cp.vl["YAW_RATE"]["YawRate"]
        self.ax_sensor = cp.vl["AXAY"]["Ax"]

        # ===================== 手刹 =====================
        ret.parkingBrake = False

        # ===================== Bus 2 原厂 MPC 帧缓存 =====================
        # 关键: 复制原厂 MPC 的完整信号值，供 carcontroller 透传
        self.cam_lkas = copy.copy(cp_cam.vl["ACC_MPC_STATE"])
        self.cam_acc = copy.copy(cp_cam.vl["ACC_CMD"])
        self.cam_adas = copy.copy(cp_cam.vl["ACC_HUD_ADAS"])
        self.esc_eps = copy.copy(cp.vl["ACC_EPS_STATE"])

        # 原厂 counter 值 (供 carcontroller 首帧接续)
        self.acc_mpc_state_counter = int(cp_cam.vl["ACC_MPC_STATE"]["COUNTER"])
        self.acc_cmd_counter = int(cp_cam.vl["ACC_CMD"]["COUNTER"])
        self.acc_hud_adas_counter = int(cp_cam.vl["ACC_HUD_ADAS"]["COUNTER"])

        # MPC 原厂 LKAS 状态 (供 fake 792 透传给 MPC)
        self.mpc_laks_output = cp_cam.vl["ACC_MPC_STATE"]["LKAS_Output"]
        self.mpc_laks_reqprepare = cp_cam.vl["ACC_MPC_STATE"]["LKAS_ReqPrepare"] != 0
        self.mpc_laks_active = cp_cam.vl["ACC_MPC_STATE"]["LKAS_Active"] != 0

        return ret, ret_sp

    def _parse_gear(self, gear: int) -> GearShifter:
        gear_map = {1: GearShifter.park, 2: GearShifter.reverse, 3: GearShifter.neutral, 4: GearShifter.drive}
        return gear_map.get(gear, GearShifter.unknown)

    def _parse_button_events(self, cp, main_on: bool) -> list:
        events = []

        if main_on != self.main_on_prev:
            events.append(structs.CarState.ButtonEvent(type=ButtonType.mainCruise, pressed=main_on))
        self.main_on_prev = main_on

        cruise_buttons = int(cp.vl["PCM_BUTTONS"]["BTN_AccUpDown_Cmd"])
        events.extend(create_button_events(cruise_buttons, self.cruise_buttons_prev, CRUISE_BUTTONS_DICT, unpressed_btn=0))
        self.cruise_buttons_prev = cruise_buttons

        cancel_button = int(cp.vl["PCM_BUTTONS"]["BTN_AccCancel"])
        events.extend(create_button_events(cancel_button, self.cancel_button_prev, {1: ButtonType.cancel}, unpressed_btn=0))
        self.cancel_button_prev = cancel_button

        activate_button = int(cp.vl["PCM_BUTTONS"]["BTN_AccActivate"])
        events.extend(create_button_events(activate_button, self.activate_button_prev, ACTIVATE_BUTTON_DICT, unpressed_btn=0))
        self.activate_button_prev = activate_button

        distance_decrease = int(cp.vl["PCM_BUTTONS"]["BTN_AccDistanceDecrease"])
        events.extend(create_button_events(distance_decrease, self.distance_decrease_prev, {1: ButtonType.gapAdjustCruise}, unpressed_btn=0))
        self.distance_decrease_prev = distance_decrease

        distance_increase = int(cp.vl["PCM_BUTTONS"]["BTN_AccDistanceIncrease"])
        events.extend(create_button_events(distance_increase, self.distance_increase_prev, {1: ButtonType.gapAdjustCruise}, unpressed_btn=0))
        self.distance_increase_prev = distance_increase

        return events

    def update_button_enable(self, buttonEvents: list) -> bool:
        if not self.CP.pcmCruise:
            for b in buttonEvents:
                if b.type in (ButtonType.accelCruise, ButtonType.decelCruise, ButtonType.setCruise) and not b.pressed:
                    return True
        return False

    @staticmethod
    def get_can_parsers(CP, CP_SP) -> dict[StrEnum, CANParser]:
        # Bus 0 messages
        messages_bus0 = [
            ("EPS", 40),
            ("CARSPEED", 20),
            ("DRIVE_STATE", 20),
            ("PEDAL", 20),
            ("EPB", float('nan')),
            ("PCM_BUTTONS", 8),
            ("ACC_EPS_STATE", float('nan')),
            ("YAW_RATE", 20),
            ("AXAY", 20),
            ("BCM", float('nan')),
            ("STALKS", float('nan')),
        ]

        # Bus 2 messages — 原厂 MPC 帧 (关键新增!)
        # 读取 MPC 原厂信号值，供 carcontroller 透传
        messages_bus2 = [
            ("ACC_MPC_STATE", 20),   # 790 原厂 LKAS 控制
            ("ACC_HUD_ADAS", 20),    # 813 原厂 HUD
            ("ACC_CMD", 20),         # 814 原厂 ACC 指令
        ]

        return {
            Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus0, CanBus.MAIN),
            Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus2, CanBus.CAM),
        }
