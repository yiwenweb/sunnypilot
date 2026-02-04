# BYD车辆状态解析 - sunnypilot 0.10.1
# 专为比亚迪18款唐DM及其他BYD车型优化
# 版本: 2026.02 稳定版

from enum import StrEnum

from opendbc.can import CANParser
from opendbc.car import Bus, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarStateBase
from opendbc.car.byd.values import DBC, CAR

ButtonType = structs.CarState.ButtonEvent.Type
GearShifter = structs.CarState.GearShifter


class CarState(CarStateBase):
    """BYD车辆状态解析类"""

    def __init__(self, CP, CP_SP):
        super().__init__(CP, CP_SP)
        self.frame = 0

        # 按钮状态
        self.cruise_buttons_prev = 0
        self.main_on_prev = False

        # LKAS状态
        self.lkas_active = False
        self.lkas_prepared = False

        # 转向状态
        self.steer_torque_driver = 0
        self.steer_torque_motor = 0

    def update(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
        cp = can_parsers[Bus.pt]

        ret = structs.CarState()
        ret_sp = structs.CarStateSP()

        self.frame += 1

        # ========== 车速解析 ==========
        # 从EPS报文获取车速 (更精确)
        if self.CP.carFingerprint == CAR.BYD_TANG_DM_2018:
            # 唐DM使用CARSPEED报文
            ret.vEgoRaw = cp.vl["CARSPEED"]["CarDisplaySpeed"] * CV.KPH_TO_MS
        else:
            ret.vEgoRaw = cp.vl["CARSPEED"]["CarDisplaySpeed"] * CV.KPH_TO_MS

        ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
        ret.standstill = ret.vEgo < 0.1

        # ========== 转向角度解析 ==========
        ret.steeringAngleDeg = cp.vl["EPS"]["SteeringAngle"]
        ret.steeringRateDeg = cp.vl["EPS"]["SteeringAngleRate"]

        # ========== 转向扭矩解析 ==========
        self.steer_torque_driver = cp.vl["ACC_EPS_STATE"]["SteerDriverTorque"]
        self.steer_torque_motor = cp.vl["ACC_EPS_STATE"]["MainTorque"]
        ret.steeringTorque = self.steer_torque_driver
        ret.steeringTorqueEps = self.steer_torque_motor

        # 驾驶员是否在转向 (扭矩超过阈值)
        ret.steeringPressed = abs(self.steer_torque_driver) > 100

        # ========== 档位解析 ==========
        gear = cp.vl["DRIVE_STATE"]["Gear"]
        ret.gearShifter = self._parse_gear(gear)

        # ========== 踏板状态 ==========
        ret.gasPressed = cp.vl["PEDAL"]["AcceleratorPedal"] > 0.01
        ret.brakePressed = cp.vl["DRIVE_STATE"]["BrakePressed"] == 1

        # ========== 转向灯状态 ==========
        ret.leftBlinker = cp.vl["STALKS"]["LeftIndicator"] == 1
        ret.rightBlinker = cp.vl["STALKS"]["RightIndicator"] == 1

        # ========== 车门状态 ==========
        ret.doorOpen = any([
            cp.vl["BCM"]["FrontLeftDoor"],
            cp.vl["BCM"]["FrontRightDoor"],
            cp.vl["BCM"]["RearLeftDoor"],
            cp.vl["BCM"]["RearRightDoor"],
        ])

        # ========== 安全带状态 ==========
        ret.seatbeltUnlatched = cp.vl["BCM"]["DriverSeatBeltFasten"] == 0

        # ========== 巡航控制状态 ==========
        # ACC状态解析
        acc_state = cp.vl["ACC_HUD_ADAS"]["AccState"]
        ret.cruiseState.available = acc_state in (2, 3, 5)  # ACC_ON, ACC_ACTIVE, FORCE_ACCEL
        ret.cruiseState.enabled = acc_state == 3  # ACC_ACTIVE
        ret.cruiseState.standstill = cp.vl["ACC_CMD"]["StandstillState"] == 1

        # 设定速度
        ret.cruiseState.speed = cp.vl["ACC_HUD_ADAS"]["SetSpeed"] * CV.KPH_TO_MS

        # 主开关状态
        main_on = cp.vl["PCM_BUTTONS"]["BTN_TOGGLE_ACC_OnOff"] == 1
        ret.cruiseState.available = main_on

        # ========== 按钮事件 ==========
        ret.buttonEvents = self._parse_button_events(cp, main_on)

        # ========== LKAS状态 ==========
        self.lkas_active = cp.vl["ACC_MPC_STATE"]["LKAS_Active"] == 1
        self.lkas_prepared = cp.vl["ACC_EPS_STATE"]["LKAS_Prepared"] == 1

        # ========== 横摆角速度和加速度 ==========
        ret.yawRate = cp.vl["YAW_RATE"]["YawRate"]

        # ========== 盲点监测 ==========
        if "BSD_RADAR" in cp.vl:
            ret.leftBlindspot = cp.vl["BSD_RADAR"]["LEFT_APPROACH"] > 0
            ret.rightBlindspot = cp.vl["BSD_RADAR"]["RIGHT_APPROACH"] > 0

        # ========== 驻车制动 ==========
        ret.parkingBrake = cp.vl["EPB"]["EPB_ActiveFlag"] == 1

        return ret, ret_sp

    def _parse_gear(self, gear: int) -> GearShifter:
        """解析档位"""
        gear_map = {
            1: GearShifter.park,
            2: GearShifter.reverse,
            3: GearShifter.neutral,
            4: GearShifter.drive,
        }
        return gear_map.get(gear, GearShifter.unknown)

    def _parse_button_events(self, cp, main_on: bool) -> list:
        """解析按钮事件"""
        events = []

        # 主开关切换
        if main_on != self.main_on_prev:
            events.append(structs.CarState.ButtonEvent(
                type=ButtonType.altButton1,
                pressed=main_on,
            ))
        self.main_on_prev = main_on

        # 巡航按钮
        cruise_buttons = cp.vl["PCM_BUTTONS"]["BTN_AccUpDown_Cmd"]
        if cruise_buttons != self.cruise_buttons_prev:
            if cruise_buttons == 1:  # SET/减速
                events.append(structs.CarState.ButtonEvent(
                    type=ButtonType.decelCruise,
                    pressed=True,
                ))
            elif cruise_buttons == 3:  # RES/加速
                events.append(structs.CarState.ButtonEvent(
                    type=ButtonType.accelCruise,
                    pressed=True,
                ))
            elif cruise_buttons == 0 and self.cruise_buttons_prev != 0:
                # 按钮释放
                if self.cruise_buttons_prev == 1:
                    events.append(structs.CarState.ButtonEvent(
                        type=ButtonType.decelCruise,
                        pressed=False,
                    ))
                elif self.cruise_buttons_prev == 3:
                    events.append(structs.CarState.ButtonEvent(
                        type=ButtonType.accelCruise,
                        pressed=False,
                    ))
        self.cruise_buttons_prev = cruise_buttons

        # 取消按钮
        if cp.vl["PCM_BUTTONS"]["BTN_AccCancel"] == 1:
            events.append(structs.CarState.ButtonEvent(
                type=ButtonType.cancel,
                pressed=True,
            ))

        # 跟车距离按钮
        if cp.vl["PCM_BUTTONS"]["BTN_AccDistanceDecrease"] == 1:
            events.append(structs.CarState.ButtonEvent(
                type=ButtonType.gapAdjustCruise,
                pressed=True,
            ))
        if cp.vl["PCM_BUTTONS"]["BTN_AccDistanceIncrease"] == 1:
            events.append(structs.CarState.ButtonEvent(
                type=ButtonType.gapAdjustCruise,
                pressed=True,
            ))

        return events

    @staticmethod
    def get_can_parsers(CP, CP_SP) -> dict[StrEnum, CANParser]:
        """获取CAN解析器"""
        messages = [
            # 基础报文 - 20Hz
            ("EPS", 20),
            ("CARSPEED", 20),
            ("DRIVE_STATE", 20),
            ("PEDAL", 20),
            ("YAW_RATE", 20),

            # 车身报文 - 10Hz
            ("BCM", 10),
            ("STALKS", 10),
            ("EPB", 10),

            # ACC/LKAS报文 - 20Hz
            ("ACC_MPC_STATE", 20),
            ("ACC_EPS_STATE", 20),
            ("ACC_HUD_ADAS", 20),
            ("ACC_CMD", 20),
            ("PCM_BUTTONS", 20),

            # 雷达报文 - 20Hz
            ("RADAR_MRR", 20),
            ("BSD_RADAR", 10),
        ]

        return {
            Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], messages, 0),
        }
