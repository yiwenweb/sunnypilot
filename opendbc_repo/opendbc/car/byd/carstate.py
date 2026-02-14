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
from opendbc.car.byd.values import DBC, STEER_THRESHOLD

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

        # ===================== 车速解析 (CarDisplaySpeed) =====================
        # DBC 定义: CarDisplaySpeed : 0|12@1+ (0.0735,0) [0|255] "km/h"
        # CANParser 自动应用 scale=0.0735，返回值已经是物理车速 km/h
        v_ego_kmh = cp.vl["CARSPEED"]["CarDisplaySpeed"]
        ret.vEgoRaw = v_ego_kmh * CV.KPH_TO_MS

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

        # 方向盘脱手检测：使用 STEER_THRESHOLD（values.py 中定义为 50）
        ret.steeringPressed = self.update_steering_pressed(abs(self.steer_torque_driver) > STEER_THRESHOLD, 5)

        # ===================== 转向故障检测（匹配EPS保护机制） =====================
        # 注意：SteerErrorCode/TorqueFailed/SteerWarning 均为 [UNVERIFIED] 信号
        # 在实车验证这些信号含义之前，不能用于触发 steerFaultPermanent
        # 否则 EPS 正常报文中的非零 bit 会被误判为故障 → "LKAS Fault: Restart the car"
        torque_failed = cp.vl["ACC_EPS_STATE"]["TorqueFailed"] == 1
        steer_warning = cp.vl["ACC_EPS_STATE"]["SteerWarning"] == 1

        # 临时故障：连续5帧TorqueFailed/SteerWarning
        if torque_failed or steer_warning:
            self.steer_fault_count += 1
            ret.steerFaultTemporary = self.steer_fault_count >= self.TORQUE_FAILED_THRESHOLD
        else:
            self.steer_fault_count = 0
            ret.steerFaultTemporary = False

        # 永久故障：暂时禁用，等实车验证 SteerErrorCode 信号含义后再启用
        # 原来的逻辑会把 EPS 正常报文中 bits 5-7 的非零值误判为故障
        ret.steerFaultPermanent = False

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
        # 全总线嗅探确认: BCM (301) 1.5Hz, STALKS (307) 1.9Hz 均在 Bus 0 上
        # 转向灯: STALKS (307) LeftIndicator/RightIndicator
        ret.leftBlinker, ret.rightBlinker = self.update_blinker_from_stalk(
            100,  # blinker_time: 保持亮 100 帧（~1秒 at 100Hz update rate）
            cp.vl["STALKS"]["LeftIndicator"] == 1,
            cp.vl["STALKS"]["RightIndicator"] == 1,
        )

        # 车门: BCM (301) — 任一车门打开即为 True
        ret.doorOpen = any([
            cp.vl["BCM"]["FrontLeftDoor"],
            cp.vl["BCM"]["FrontRightDoor"],
            cp.vl["BCM"]["RearLeftDoor"],
            cp.vl["BCM"]["RearRightDoor"],
            cp.vl["BCM"]["BootDoor"],
        ])

        # 安全带: BCM (301) DriverSeatBeltFasten — 1=已系, 0=未系
        ret.seatbeltUnlatched = cp.vl["BCM"]["DriverSeatBeltFasten"] == 0

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
        # 全总线嗅探确认: YAW_RATE (546) 50Hz, AXAY (547) 50Hz 均在 Bus 0 上
        # YawRate: 12-bit, scale 0.002133, offset -2.094, 单位 rad/s
        ret.yawRate = cp.vl["YAW_RATE"]["YawRate"]
        # Ax: 12-bit, scale 0.027167, offset -21.593, 单位 m/s²
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
        # 全总线嗅探数据 (sniff_all_buses.py, 22.9秒采样):
        #   EPS: 100Hz, CARSPEED/DRIVE_STATE/PEDAL/ACC_EPS_STATE/YAW_RATE/AXAY: 50Hz
        #   PCM_BUTTONS/BELT: 20Hz, BCM/STALKS: ~1.5-2Hz, EPB: 1Hz
        #
        # 频率设置策略: 实际频率的 40%，给予充足容忍度
        # BCM/STALKS: 低频消息用 float('nan') 跳过存活检查
        # ACC_EPS_STATE: 用 float('nan') 因为 openpilot 未激活时 EPS 可能不发 792
        messages_bus0 = [
            ("EPS", 40),              # 实际 100Hz，设 40Hz（超时 250ms）
            ("CARSPEED", 20),         # 实际 50Hz，设 20Hz（超时 500ms）
            ("DRIVE_STATE", 20),      # 实际 50Hz，设 20Hz
            ("PEDAL", 20),            # 实际 50Hz，设 20Hz
            ("EPB", float('nan')),    # 实际 1Hz，低频消息跳过存活检查
            ("PCM_BUTTONS", 8),       # 实际 20Hz，设 8Hz（超时 1.25s）
            ("ACC_EPS_STATE", float('nan')),  # 50Hz 但可能在某些状态下不发送
            ("YAW_RATE", 20),         # 实际 50Hz，设 20Hz
            ("AXAY", 20),             # 实际 50Hz，设 20Hz
            ("BCM", float('nan')),    # 实际 ~1.5Hz，低频消息跳过存活检查
            ("STALKS", float('nan')), # 实际 ~2Hz，低频消息跳过存活检查
        ]

        return {
            Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus0, 0),
        }