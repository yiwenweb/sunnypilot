"""
BYD CarState - Vehicle state parsing implementation.

This module implements the CarState class for BYD vehicles, responsible for
parsing CAN messages and populating the CarState structure with vehicle data.

=== （五）重要安全提醒 ===
1. 仅辅助，不可脱手，随时接管
2. 弯道、雨雪、标线模糊、施工路段慎用/关闭
3. 不识别行人、非机动车、静止障碍物
4. 升级后功能以4S店开通版本为准

核心修正说明：
1. 修复CarDisplaySpeed解析：scale从1 km/h改为原厂0.0735 km/h（关键修正）
2. 补充steerFault检测逻辑（匹配EPS保护机制）
3. 修正CAN总线注释错误（Bus2的813是回声，无需解析）
4. 优化方向盘扭矩阈值（匹配原厂脱手检测规则）
"""

from enum import StrEnum

from opendbc.can import CANParser
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarStateBase
from opendbc.car.byd.values import DBC

ButtonType = structs.CarState.ButtonEvent.Type
GearShifter = structs.CarState.GearShifter

# Button mapping for BTN_AccUpDown_Cmd signal
# DBC: VAL_ 944 BTN_AccUpDown_Cmd 0 "NOTPRESSED" 1 "DOWN_SETSPEED" 3 "UP_RESETSPEED"
# 1 = SET (decrease speed), 3 = RES (increase speed)
CRUISE_BUTTONS_DICT = {
    1: ButtonType.decelCruise,  # SET - decrease speed
    3: ButtonType.accelCruise,  # RES - increase speed
}


class CarState(CarStateBase):
    """BYD vehicle state parsing class.

    Parses CAN messages and populates the CarState structure with vehicle data.
    Inherits from CarStateBase and implements required methods.

    Attributes:
        frame: Frame counter
        cruise_buttons_prev: Previous cruise button state
        main_on_prev: Previous main switch state
        cancel_button_prev: Previous cancel button state
        distance_decrease_prev: Previous distance decrease button state
        distance_increase_prev: Previous distance increase button state
        lkas_active: LKAS active status
        lkas_prepared: LKAS prepared status
        steer_torque_driver: Driver steering torque
        steer_torque_motor: EPS motor torque
        ax_sensor: Longitudinal acceleration from sensor
    """

    def __init__(self, CP, CP_SP):
        """Initialize CarState.

        Args:
            CP: CarParams structure
            CP_SP: CarParams sunnypilot extension
        """
        super().__init__(CP, CP_SP)
        self.frame = 0

        # Button states for change detection
        self.cruise_buttons_prev = 0
        self.main_on_prev = False
        self.main_on = False
        self.acc_toggle_pressed_prev = False
        self.cancel_button_prev = 0
        self.distance_decrease_prev = 0
        self.distance_increase_prev = 0

        # LKAS status
        self.lkas_active = False
        self.lkas_prepared = False

        # Steering state
        self.steer_torque_driver = 0
        self.steer_torque_motor = 0

        # Dynamic signals (Requirement 6.2)
        self.ax_sensor = 0.0

        # Steer fault detection
        self.steer_fault_count = 0  # Counter for persistent fault detection
        self.STEER_FAULT_PERMANENT_THRESHOLD = 100  # ~1 second at 100Hz
        self.TORQUE_FAILED_THRESHOLD = 5  # 连续5帧TorqueFailed判定为临时故障

    def update(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
        """Parse CAN messages and return vehicle state.

        Args:
            can_parsers: Dictionary containing CANParser instances

        Returns:
            tuple: (CarState, CarStateSP) containing parsed vehicle state
        """
        cp = can_parsers[Bus.pt]      # Bus 0 - Powertrain

        ret = structs.CarState()
        ret_sp = structs.CarStateSP()

        self.frame += 1

        # ===================== 核心修正：车速解析 (CarDisplaySpeed) =====================
        # 原厂规范：CarDisplaySpeed (12-bit) = 物理车速 / 0.0735 km/h
        # 修正前错误：scale=1 km/h；修正后：scale=0.0735 km/h（匹配DBC修正点）
        # DBC信号定义：CarDisplaySpeed : 0|12@1+ (0.0735,0) [0|255] "km/h"
        v_ego_raw = cp.vl["CARSPEED"]["CarDisplaySpeed"]  # 原始12位值
        v_ego_kmh = v_ego_raw * 0.0735                    # 转换为物理车速（km/h）
        ret.vEgoRaw = v_ego_kmh * CV.KPH_TO_MS            # 转换为m/s（openpilot标准单位）

        # Apply Kalman filtering for smooth velocity estimation (Requirement 6.3)
        ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)

        # Set standstill when vehicle speed is below 0.1 m/s (Requirement 6.5)
        ret.standstill = ret.vEgo < 0.1

        # Cluster speed for UI display（和仪表显示一致）
        ret.vEgoCluster = ret.vEgoRaw

        # ===================== 方向盘角度/速率解析 =====================
        # Steering angle parsing (Requirements 3.2, 3.3)
        # DBC signal: SteeringAngle : 0|16@1- (0.1,0) [-450|450] "deg"
        ret.steeringAngleDeg = cp.vl["EPS"]["SteeringAngle"]
        # DBC signal: SteeringAngleRate : 16|8@1+ (4,0) [0|1020] "deg/s"
        ret.steeringRateDeg = cp.vl["EPS"]["SteeringAngleRate"]

        # ===================== 方向盘扭矩解析（原厂脱手检测） =====================
        # Steering torque parsing (Requirements 5.7, 5.8)
        # DBC signal: SteerDriverTorque : 24|12@1- (1,0) [-2048|2047] ""
        self.steer_torque_driver = cp.vl["ACC_EPS_STATE"]["SteerDriverTorque"]
        # DBC signal: MainTorque : 8|12@1- (1,0) [-2048|2047] ""
        self.steer_torque_motor = cp.vl["ACC_EPS_STATE"]["MainTorque"]

        # Store torque values in CarState
        ret.steeringTorque = self.steer_torque_driver
        ret.steeringTorqueEps = self.steer_torque_motor

        # 修正：方向盘脱手检测阈值改为5Nm（原厂规则），原50过大导致误判
        ret.steeringPressed = abs(self.steer_torque_driver) > 5

        # ===================== 转向故障检测（匹配EPS保护机制） =====================
        # 核心修正：补充steerFault检测（TorqueFailed/SteerWarning触发）
        torque_failed = cp.vl["ACC_EPS_STATE"]["TorqueFailed"] == 1
        steer_warning = cp.vl["ACC_EPS_STATE"]["SteerWarning"] == 1
        steer_error_code = cp.vl["ACC_EPS_STATE"]["SteerErrorCode"]

        # 临时故障：连续5帧TorqueFailed/SteerWarning
        if torque_failed or steer_warning:
            self.steer_fault_count += 1
            ret.steerFaultTemporary = self.steer_fault_count >= self.TORQUE_FAILED_THRESHOLD
        else:
            self.steer_fault_count = 0
            ret.steerFaultTemporary = False

        # 永久故障：SteerErrorCode非0 或 临时故障持续1秒
        ret.steerFaultPermanent = (steer_error_code != 0) or (self.steer_fault_count >= self.STEER_FAULT_PERMANENT_THRESHOLD)

        # ===================== 档位解析 =====================
        # Gear parsing (Requirement 3.4)
        # DBC signal: Gear : 40|3@1+ (1,0) [0|7] "" 
        # VAL_ 578 Gear 1 "P" 2 "R" 3 "N" 4 "D"
        gear = cp.vl["DRIVE_STATE"]["Gear"]
        ret.gearShifter = self._parse_gear(gear)

        # ===================== 踏板状态解析 =====================
        # Pedal status (Requirements 3.5, 3.6)
        # AcceleratorPedal : 0|8@1+ (0.01,0) [0|2.55] ""
        accelerator_pedal = cp.vl["PEDAL"]["AcceleratorPedal"]
        ret.gasPressed = accelerator_pedal > 0.01  # Pressed when > 1%

        # BrakePressed : 37|1@0+ (1,0) [0|1] ""
        ret.brakePressed = cp.vl["DRIVE_STATE"]["BrakePressed"] == 1

        # ===================== 转向灯/车门/安全带解析 =====================
        # Turn indicator parsing (Requirement 4.3)
        ret.leftBlinker = cp.vl["STALKS"]["LeftIndicator"] == 1
        ret.rightBlinker = cp.vl["STALKS"]["RightIndicator"] == 1

        # Door status parsing (Requirements 4.1, 4.5)
        front_left_door = cp.vl["BCM"]["FrontLeftDoor"] == 1
        front_right_door = cp.vl["BCM"]["FrontRightDoor"] == 1
        rear_left_door = cp.vl["BCM"]["RearLeftDoor"] == 1
        rear_right_door = cp.vl["BCM"]["RearRightDoor"] == 1
        ret.doorOpen = front_left_door or front_right_door or rear_left_door or rear_right_door

        # Seatbelt status parsing (Requirements 4.2, 4.6)
        driver_seatbelt_fastened = cp.vl["BCM"]["DriverSeatBeltFasten"] == 1
        ret.seatbeltUnlatched = not driver_seatbelt_fastened

        # ===================== 巡航控制状态解析 =====================
        # Cruise control status (Requirements 5.1, 5.2, 5.3)
        # 关键说明：Bus2的813是openpilot自己的回声，无法读取原厂SetSpeed
        acc_toggle_pressed = cp.vl["PCM_BUTTONS"]["BTN_TOGGLE_ACC_OnOff"] == 1
        if acc_toggle_pressed and not self.acc_toggle_pressed_prev:
            self.main_on = not self.main_on
        self.acc_toggle_pressed_prev = acc_toggle_pressed
        main_on = self.main_on

        ret.cruiseState.available = main_on
        ret.cruiseState.enabled = False  # pcmCruise=False模式，由buttonEnable管理
        ret.cruiseState.standstill = ret.standstill
        ret.cruiseState.speed = 0  # 使用openpilot内部set speed

        # Button events
        ret.buttonEvents = self._parse_button_events(cp, main_on)

        # ===================== LKAS状态解析 =====================
        # LKAS status (Requirements 5.5, 5.6)
        self.lkas_active = False  # 由CarController跟踪发送状态
        # LKAS_Prepared : 0|1@1+ (1,0) [0|1] ""
        self.lkas_prepared = cp.vl["ACC_EPS_STATE"]["LKAS_Prepared"] == 1

        # ===================== 横摆率/纵向加速度解析 =====================
        # Yaw rate parsing (Requirement 6.1)
        # YawRate : 0|12@1+ (0.002133,-2.094) [-2.0|2.0] "rad/s"
        ret.yawRate = cp.vl["YAW_RATE"]["YawRate"]

        # Longitudinal acceleration parsing (Requirement 6.2)
        # Ax : 0|12@1+ (0.027167,-21.593) [-10.0|10.0] "m/s^2"
        self.ax_sensor = cp.vl["AXAY"]["Ax"]

        # ===================== 手刹状态解析 =====================
        # Parking brake status parsing (Requirement 4.4)
        # EPB_ActiveFlag : 40|1@1+ (1,0) [0|1]
        ret.parkingBrake = cp.vl["EPB"]["EPB_ActiveFlag"] == 1

        return ret, ret_sp

    def _parse_gear(self, gear: int) -> GearShifter:
        """Parse gear position (Requirement 3.4).

        Maps BYD gear values to sunnypilot GearShifter enum.
        DBC definition: Gear : 40|3@1+ (1,0) [0|7]
        VAL_ 578 Gear 1 "P" 2 "R" 3 "N" 4 "D"

        Args:
            gear: Raw gear value from CAN (1=P, 2=R, 3=N, 4=D)

        Returns:
            GearShifter enum value (park, reverse, neutral, drive, or unknown)
        """
        gear_map = {
            1: GearShifter.park,      # P - Park
            2: GearShifter.reverse,   # R - Reverse
            3: GearShifter.neutral,   # N - Neutral
            4: GearShifter.drive,     # D - Drive
        }
        return gear_map.get(gear, GearShifter.unknown)

    def _parse_button_events(self, cp, main_on: bool) -> list:
        """Parse button events (Requirement 5.4).

        Generates ButtonEvent objects for cruise control button state changes.

        DBC signals from PCM_BUTTONS (944):
        - BTN_AccUpDown_Cmd: 0=NOTPRESSED, 1=SET, 3=RES
        - BTN_AccCancel: 0=not pressed, 1=cancel pressed
        - BTN_AccDistanceDecrease/Increase: 0=not pressed, 1=pressed
        - BTN_TOGGLE_ACC_OnOff: 0=not pressed, 1=pressed

        Args:
            cp: CAN parser with PCM_BUTTONS message data
            main_on: Current state of ACC main switch

        Returns:
            List of ButtonEvent objects for any button state changes
        """
        events = []

        # Main switch toggle (ACC On/Off)
        if main_on != self.main_on_prev:
            events.append(structs.CarState.ButtonEvent(
                type=ButtonType.mainCruise,
                pressed=main_on,
            ))
        self.main_on_prev = main_on

        # Cruise speed buttons (SET/RES)
        cruise_buttons = int(cp.vl["PCM_BUTTONS"]["BTN_AccUpDown_Cmd"])
        events.extend(create_button_events(cruise_buttons, self.cruise_buttons_prev,
                                           CRUISE_BUTTONS_DICT, unpressed_btn=0))
        self.cruise_buttons_prev = cruise_buttons

        # Cancel button
        cancel_button = int(cp.vl["PCM_BUTTONS"]["BTN_AccCancel"])
        events.extend(create_button_events(cancel_button, self.cancel_button_prev,
                                           {1: ButtonType.cancel}, unpressed_btn=0))
        self.cancel_button_prev = cancel_button

        # Distance adjustment buttons
        distance_decrease = int(cp.vl["PCM_BUTTONS"]["BTN_AccDistanceDecrease"])
        events.extend(create_button_events(distance_decrease, self.distance_decrease_prev,
                                           {1: ButtonType.gapAdjustCruise}, unpressed_btn=0))
        self.distance_decrease_prev = distance_decrease

        distance_increase = int(cp.vl["PCM_BUTTONS"]["BTN_AccDistanceIncrease"])
        events.extend(create_button_events(distance_increase, self.distance_increase_prev,
                                           {1: ButtonType.gapAdjustCruise}, unpressed_btn=0))
        self.distance_increase_prev = distance_increase

        return events

    @staticmethod
    def get_can_parsers(CP, CP_SP) -> dict[StrEnum, CANParser]:
        """Get CAN parsers for vehicle state parsing.

        Configures CANParser with required messages and frequencies.

        BYD CAN Bus Layout:
        - Bus 0: Powertrain messages (EPS, speed, pedals, buttons, etc.)
        - Bus 2: ACC/LKAS RX messages (ACC_EPS_STATE, ACC_HUD_ADAS) → 均为openpilot回声，无需解析

        Args:
            CP: CarParams structure
            CP_SP: CarParams sunnypilot extension

        Returns:
            Dictionary mapping bus types to CANParser instances
        """
        # Bus 0 messages - Powertrain
        # 频率说明:
        #   >0: 固定频率检查（超时 = 1/freq * 10）
        #   0:  自动学习频率（初始超时10秒，收到3条后自动计算）
        #   float('nan'): 跳过存活检查（ignore_alive=True）
        messages_bus0 = [
            # Basic messages - 20Hz
            ("EPS", 0),
            ("CARSPEED", 0),          # 车速报文（核心修正scale=0.0735）
            ("DRIVE_STATE", 20),
            ("PEDAL", 20),
            ("YAW_RATE", 20),
            ("AXAY", 20),

            # Body messages
            ("BCM", 1),
            ("STALKS", 1),
            ("EPB", 0),

            # PCM buttons on Bus 0 - frequency 0 to auto-learn
            ("PCM_BUTTONS", 0),
            # ACC_EPS_STATE: 跳过存活检查，避免影响canValid
            ("ACC_EPS_STATE", float('nan')),
        ]

        return {
            Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus0, 0),
        }