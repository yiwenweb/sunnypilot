"""
BYD CarState - Vehicle state parsing implementation.

This module implements the CarState class for BYD vehicles, responsible for
parsing CAN messages and populating the CarState structure with vehicle data.
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

        # Vehicle speed parsing (Requirements 3.1, 6.3, 6.4, 6.5)
        # Parse vehicle display speed from CARSPEED message (12-bit unsigned, 1 km/h scale)
        # DBC signal: CarDisplaySpeed : 0|12@1+ (1,0) [0|255] "km/h"
        v_ego_raw_kmh = cp.vl["CARSPEED"]["CarDisplaySpeed"]
        
        # Convert km/h to m/s using CV.KPH_TO_MS constant (Requirement 3.1)
        ret.vEgoRaw = v_ego_raw_kmh * CV.KPH_TO_MS
        
        # Apply Kalman filtering for smooth velocity estimation (Requirement 6.3)
        # update_speed_kf returns (filtered_speed, acceleration) tuple
        # The Kalman filter provides smooth velocity and calculates acceleration (Requirement 6.4)
        ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
        
        # Set standstill when vehicle speed is below 0.1 m/s (Requirement 6.5)
        ret.standstill = ret.vEgo < 0.1

        # Steering angle parsing (Requirements 3.2, 3.3)
        # Parse steering angle from EPS message (Requirement 3.2)
        # DBC signal: SteeringAngle : 0|16@1- (0.1,0) [-450|450] "deg"
        # The 0.1 degree scale is applied by CANParser via DBC definition
        # Raw 16-bit signed value is automatically converted to degrees
        ret.steeringAngleDeg = cp.vl["EPS"]["SteeringAngle"]
        
        # Parse steering angle rate from EPS message (Requirement 3.3)
        # DBC signal: SteeringAngleRate : 16|8@1+ (4,0) [0|1020] "deg/s"
        # The scale factor of 4 is applied by CANParser via DBC definition
        # Raw 8-bit unsigned value is automatically converted to deg/s
        ret.steeringRateDeg = cp.vl["EPS"]["SteeringAngleRate"]

        # Steering torque parsing (Requirements 5.7, 5.8)
        # Parse driver steering torque from ACC_EPS_STATE message (Requirement 5.7)
        # DBC signal: SteerDriverTorque : 24|12@1- (1,0) [-2048|2047] "" MPC,VCU
        # 12-bit signed value representing driver applied torque to steering wheel
        # Positive values = clockwise torque, Negative values = counter-clockwise torque
        self.steer_torque_driver = cp.vl["ACC_EPS_STATE"]["SteerDriverTorque"]
        
        # Parse motor (EPS) steering torque from ACC_EPS_STATE message (Requirement 5.8)
        # DBC signal: MainTorque : 8|12@1- (1,0) [-2048|2047] "" MPC
        # 12-bit signed value representing EPS motor output torque
        # This is the torque being applied by the electric power steering motor
        self.steer_torque_motor = cp.vl["ACC_EPS_STATE"]["MainTorque"]
        
        # Store torque values in CarState for use by CarController and other components
        ret.steeringTorque = self.steer_torque_driver
        ret.steeringTorqueEps = self.steer_torque_motor

        # Detect if driver is actively steering (steeringPressed)
        # Threshold of 50 matches old version behavior (旧版本约50)
        ret.steeringPressed = abs(self.steer_torque_driver) > 50

        # Gear parsing (Requirement 3.4)
        # Parse gear position from DRIVE_STATE message
        # DBC signal: Gear : 40|3@1+ (1,0) [0|7] "" - 3-bit unsigned value
        # VAL_ 578 Gear 1 "P" 2 "R" 3 "N" 4 "D"
        # Gear values: 1=Park, 2=Reverse, 3=Neutral, 4=Drive
        gear = cp.vl["DRIVE_STATE"]["Gear"]
        ret.gearShifter = self._parse_gear(gear)

        # Pedal status (Requirements 3.5, 3.6)
        # Parse accelerator pedal position from PEDAL message (Requirement 3.6)
        # DBC signal: AcceleratorPedal : 0|8@1+ (0.01,0) [0|2.55] ""
        # Scale is 0.01, so raw value 0-255 becomes 0-2.55 (percentage as decimal)
        # gasPressed = true when pedal position > 1% (0.01 in scaled units)
        # Note: The CANParser applies the 0.01 scale from DBC, so we compare against 0.01 (1%)
        accelerator_pedal = cp.vl["PEDAL"]["AcceleratorPedal"]
        ret.gasPressed = accelerator_pedal > 0.01  # Pressed when > 1%
        
        # Parse brake pressed status from DRIVE_STATE message (Requirement 3.5)
        # DBC signal: BrakePressed : 37|1@0+ (1,0) [0|1] "" - 1-bit boolean
        ret.brakePressed = cp.vl["DRIVE_STATE"]["BrakePressed"] == 1

        # Turn indicator parsing (Requirement 4.3)
        # Parse left and right turn indicator status from STALKS message
        # DBC signals: LeftIndicator : 4|1@0+ (1,0) [0|1], RightIndicator : 5|1@0+ (1,0) [0|1]
        # Signal values: 1 = indicator on, 0 = indicator off
        ret.leftBlinker = cp.vl["STALKS"]["LeftIndicator"] == 1
        ret.rightBlinker = cp.vl["STALKS"]["RightIndicator"] == 1

        # Door status parsing (Requirements 4.1, 4.5)
        # Parse door open status for all four doors from BCM message (Requirement 4.1)
        # DBC signals: FrontLeftDoor, FrontRightDoor, RearLeftDoor, RearRightDoor
        # Each signal is 1-bit: 1 = door open, 0 = door closed
        # doorOpen = OR(FrontLeftDoor, FrontRightDoor, RearLeftDoor, RearRightDoor) (Requirement 4.5)
        front_left_door = cp.vl["BCM"]["FrontLeftDoor"] == 1
        front_right_door = cp.vl["BCM"]["FrontRightDoor"] == 1
        rear_left_door = cp.vl["BCM"]["RearLeftDoor"] == 1
        rear_right_door = cp.vl["BCM"]["RearRightDoor"] == 1
        ret.doorOpen = front_left_door or front_right_door or rear_left_door or rear_right_door

        # Seatbelt status parsing (Requirements 4.2, 4.6)
        # Parse driver seatbelt fastened status from BCM message (Requirement 4.2)
        # DBC signal: DriverSeatBeltFasten : 6|1@0+ (1,0) [0|1]
        # Signal value: 1 = seatbelt fastened, 0 = seatbelt not fastened
        # seatbeltUnlatched = NOT(DriverSeatBeltFasten) (Requirement 4.6)
        driver_seatbelt_fastened = cp.vl["BCM"]["DriverSeatBeltFasten"] == 1
        ret.seatbeltUnlatched = not driver_seatbelt_fastened

        # Cruise control status (Requirements 5.1, 5.2, 5.3)
        # 注意: openpilot 发送 813 到 Bus 0，panda 转发到 Bus 2，
        # 所以 Bus 2 上的 813 是 openpilot 自己发的，不是原厂 MPC 的。
        # 因此不能从 Bus 2 的 813 读取 AccState。
        #
        # BTN_TOGGLE_ACC_OnOff 是状态信号（不是脉冲）:
        #   1 = ACC 已开启, 0 = ACC 已关闭
        # 直接用作 cruiseState.available
        main_on = cp.vl["PCM_BUTTONS"]["BTN_TOGGLE_ACC_OnOff"] == 1

        ret.cruiseState.available = main_on

        # cruiseState.enabled 的逻辑:
        # available=True 只表示 ACC 系统已开启（仪表显示 ACC 图标）
        # enabled=True 表示 ACC 正在主动控制车辆（用户按了 RES/SET）
        # openpilot controlsd 会在收到 accelCruise/decelCruise 按钮事件时
        # 将 enabled 设为 True，所以这里只需要设 enabled=available
        # controlsd 会根据按钮事件和条件来管理实际的 engage/disengage
        ret.cruiseState.enabled = main_on

        # Standstill state - derived from vehicle speed (Requirement 5.3)
        ret.cruiseState.standstill = ret.standstill

        # Set speed: 由于 Bus 2 的 813 是 openpilot 自己的回声，
        # 无法从中读取原厂 MPC 的 SetSpeed。
        # 设为 0，让 openpilot 使用自己内部管理的 set speed。
        ret.cruiseState.speed = 0

        # Button events
        ret.buttonEvents = self._parse_button_events(cp, main_on)

        # LKAS status (Requirements 5.5, 5.6)
        # Note: ACC_MPC_STATE (790) is a TX message, so we can't read LKAS_Active from it
        # LKAS active status will be tracked internally by CarController when sending commands
        # For now, set to False as we're not actively controlling LKAS yet
        self.lkas_active = False
        
        # Parse LKAS prepared status from ACC_EPS_STATE message (Requirement 5.6)
        # DBC signal: LKAS_Prepared : 0|1@1+ (1,0) [0|1] "" MPC
        # 1-bit boolean: 1 = EPS is ready for LKAS control, 0 = EPS not ready
        # This indicates whether the Electric Power Steering system is prepared
        # to accept LKAS steering commands from the MPC (Multi-Purpose Camera)
        self.lkas_prepared = cp.vl["ACC_EPS_STATE"]["LKAS_Prepared"] == 1

        # Yaw rate parsing (Requirement 6.1)
        # Parse yaw rate from YAW_RATE message
        # DBC signal: YawRate : 0|12@1+ (0.002133,-2.094) [-2.0|2.0] "rad/s"
        # 12-bit unsigned value with scale 0.002133 and offset -2.094
        # The CANParser applies the scale and offset from DBC automatically
        # Valid range: [-2.0, 2.0] rad/s (positive = clockwise rotation)
        # This signal is used by sunnypilot for vehicle dynamics calculations
        ret.yawRate = cp.vl["YAW_RATE"]["YawRate"]
        
        # Longitudinal acceleration parsing (Requirement 6.2 - Optional)
        # Parse longitudinal acceleration from AXAY message
        # DBC signal: Ax : 0|12@1+ (0.027167,-21.593) [-10.0|10.0] "m/s^2"
        # 12-bit unsigned value with scale 0.027167 and offset -21.593
        # The CANParser applies the scale and offset from DBC automatically
        # Valid range: [-10.0, 10.0] m/s² (positive = forward acceleration)
        # Note: aEgo is already calculated from Kalman-filtered speed (Requirement 6.4)
        # This direct sensor reading can be used for validation or future enhancements
        # Currently stored for reference but not overriding the Kalman-filtered aEgo
        self.ax_sensor = cp.vl["AXAY"]["Ax"]

        # Blind spot monitoring handled by radar_interface.py

        # Parking brake status parsing (Requirement 4.4)
        # Parse parking brake engaged status from EPB message
        # DBC signal: EPB_ActiveFlag : 40|1@1+ (1,0) [0|1]
        # Signal value: 1 = parking brake engaged, 0 = parking brake released
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
        - BTN_AccDistanceDecrease: 0=not pressed, 1=pressed
        - BTN_AccDistanceIncrease: 0=not pressed, 1=pressed
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
        - Bus 2: ACC/LKAS RX messages (ACC_EPS_STATE, ACC_HUD_ADAS)
        
        Note: ACC_MPC_STATE (790) and ACC_CMD (814) are TX messages sent by
        openpilot, not RX messages, so they are not included in the parser.
        
        Args:
            CP: CarParams structure
            CP_SP: CarParams sunnypilot extension
            
        Returns:
            Dictionary mapping bus types to CANParser instances
        """
        # Bus 0 messages - Powertrain
        messages_bus0 = [
            # Basic messages - 20Hz
            ("EPS", 0),
            ("CARSPEED", 0),
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
            # ACC_EPS_STATE frequency set to 0: when openpilot sends 790,
            # EPS behavior may change, affecting 792 timing
            ("ACC_EPS_STATE", 0),
        ]

        # Bus 2 messages - ACC/LKAS (RX only)
        # Note: Bus 2 的 813/814/815/790 都是 openpilot 通过 panda 转发的回声，
        # 不是原厂 MPC 的数据，所以不需要解析。
        messages_bus2 = []

        return {
            Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus0, 0),
            Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus2, 2),
        }
