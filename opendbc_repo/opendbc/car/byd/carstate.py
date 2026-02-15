"""
BYD CarState - based on carrotpilot by yysnet.
Parses Bus 0 (vehicle ECUs) and Bus 2 (MPC camera) signals.
"""

import copy
from enum import StrEnum

from opendbc.can import CANParser
from opendbc.car import Bus, create_button_events, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarStateBase
from opendbc.car.byd.values import DBC, CanBus

ButtonType = structs.CarState.ButtonEvent.Type
GearShifter = structs.CarState.GearShifter


class CarState(CarStateBase):
    def __init__(self, CP, CP_SP):
        super().__init__(CP, CP_SP)

        # EPS LKAS status
        self.lkas_prepared = False
        self.eps_state_counter = 0

        # Stock MPC counters (for counter continuation)
        self.acc_mpc_state_counter = 0
        self.acc_cmd_counter = 0

        # Stock MPC LKAS state (for fake 792 passthrough)
        self.mpc_lkas_output = 0
        self.mpc_lkas_active = False
        self.mpc_lkas_reqprepare = False

        # Cached stock frames for passthrough
        self.cam_lkas = {}   # ACC_MPC_STATE (790) from MPC
        self.cam_acc = {}    # ACC_CMD (814) from MPC
        self.esc_eps = {}    # ACC_EPS_STATE (792) from EPS

        # Button prev states
        self.cruise_buttons_prev = 0
        self.cancel_button_prev = 0
        self.activate_button_prev = 0
        self.main_on_prev = False
        self.distance_dec_prev = 0
        self.distance_inc_prev = 0

    def update(self, can_parsers) -> tuple[structs.CarState, structs.CarStateSP]:
        cp = can_parsers[Bus.pt]       # Bus 0
        cp_cam = can_parsers[Bus.cam]  # Bus 2

        ret = structs.CarState()
        ret_sp = structs.CarStateSP()

        # === Speed ===
        ret.vEgoRaw = cp.vl["CARSPEED"]["CarDisplaySpeed"] * CV.KPH_TO_MS
        ret.vEgo, ret.aEgo = self.update_speed_kf(ret.vEgoRaw)
        ret.standstill = ret.vEgoRaw < 0.01
        ret.vEgoCluster = ret.vEgoRaw

        # === Steering ===
        ret.steeringAngleDeg = cp.vl["EPS"]["SteeringAngle"]
        ret.steeringRateDeg = cp.vl["EPS"]["SteeringAngleRate"]
        ret.steeringTorque = cp.vl["ACC_EPS_STATE"]["SteerDriverTorque"]
        ret.steeringTorqueEps = cp.vl["ACC_EPS_STATE"]["MainTorque"]
        ret.steeringPressed = self.update_steering_pressed(abs(ret.steeringTorque) > 59, 5)

        # === Steering faults ===
        eps_warning = bool(cp.vl["ACC_EPS_STATE"]["SteerWarning"])
        acc_state = cp_cam.vl["ACC_HUD_ADAS"]["AccState"]
        ret.steerFaultTemporary = bool((acc_state == 7) or eps_warning)
        ret.steerFaultPermanent = bool(cp.vl["ACC_EPS_STATE"]["TorqueFailed"])

        # === Gear ===
        gear_map = {1: GearShifter.park, 2: GearShifter.reverse, 3: GearShifter.neutral, 4: GearShifter.drive}
        ret.gearShifter = gear_map.get(int(cp.vl["DRIVE_STATE"]["Gear"]), GearShifter.unknown)

        # === Pedals ===
        ret.gas = int(cp.vl["PEDAL"]["AcceleratorPedal"])
        ret.gasPressed = ret.gas != 0
        ret.brakePressed = cp.vl["DRIVE_STATE"]["BrakePressed"] == 1

        # === Blinkers / doors / seatbelt ===
        ret.leftBlinker = bool(cp.vl["STALKS"]["LeftIndicator"])
        ret.rightBlinker = bool(cp.vl["STALKS"]["RightIndicator"])
        ret.doorOpen = any([cp.vl["BCM"]["FrontLeftDoor"], cp.vl["BCM"]["FrontRightDoor"],
                            cp.vl["BCM"]["RearLeftDoor"], cp.vl["BCM"]["RearRightDoor"]])
        ret.seatbeltUnlatched = cp.vl["BCM"]["DriverSeatBeltFasten"] == 0

        # === Cruise state (stock longitudinal - read from MPC) ===
        main_on = bool(cp.vl["PCM_BUTTONS"]["BTN_TOGGLE_ACC_OnOff"])
        ret.cruiseState.available = main_on
        ret.cruiseState.enabled = acc_state in (3, 5)
        ret.cruiseState.standstill = ret.standstill
        ret.cruiseState.speed = cp_cam.vl["ACC_HUD_ADAS"]["SetSpeed"] * CV.KPH_TO_MS

        # === Yaw rate ===
        ret.yawRate = cp.vl["YAW_RATE"]["YawRate"]

        # === Parking brake ===
        ret.parkingBrake = False

        # === Buttons ===
        ret.buttonEvents = self._parse_buttons(cp, main_on)

        # === EPS 792 status (Bus 0) ===
        self.lkas_prepared = cp.vl["ACC_EPS_STATE"]["LKAS_Prepared"] == 1
        self.eps_state_counter = int(cp.vl["ACC_EPS_STATE"]["COUNTER_792"])

        # === Bus 2 MPC frame cache (for passthrough in carcontroller) ===
        self.cam_lkas = copy.copy(cp_cam.vl["ACC_MPC_STATE"])
        self.cam_acc = copy.copy(cp_cam.vl["ACC_CMD"])
        self.esc_eps = copy.copy(cp.vl["ACC_EPS_STATE"])

        self.acc_mpc_state_counter = int(cp_cam.vl["ACC_MPC_STATE"]["COUNTER"])
        self.acc_cmd_counter = int(cp_cam.vl["ACC_CMD"]["COUNTER"])

        self.mpc_lkas_output = cp_cam.vl["ACC_MPC_STATE"]["LKAS_Output"]
        self.mpc_lkas_reqprepare = cp_cam.vl["ACC_MPC_STATE"]["LKAS_ReqPrepare"] != 0
        self.mpc_lkas_active = cp_cam.vl["ACC_MPC_STATE"]["LKAS_Active"] != 0

        return ret, ret_sp

    def _parse_buttons(self, cp, main_on):
        events = []
        if main_on != self.main_on_prev:
            events.append(structs.CarState.ButtonEvent(type=ButtonType.mainCruise, pressed=main_on))
        self.main_on_prev = main_on

        cruise_buttons = int(cp.vl["PCM_BUTTONS"]["BTN_AccUpDown_Cmd"])
        events.extend(create_button_events(cruise_buttons, self.cruise_buttons_prev,
                       {1: ButtonType.decelCruise, 3: ButtonType.accelCruise}, unpressed_btn=0))
        self.cruise_buttons_prev = cruise_buttons

        cancel = int(cp.vl["PCM_BUTTONS"]["BTN_AccCancel"])
        events.extend(create_button_events(cancel, self.cancel_button_prev, {1: ButtonType.cancel}, unpressed_btn=0))
        self.cancel_button_prev = cancel

        activate = int(cp.vl["PCM_BUTTONS"]["BTN_AccActivate"])
        events.extend(create_button_events(activate, self.activate_button_prev, {1: ButtonType.setCruise}, unpressed_btn=0))
        self.activate_button_prev = activate

        dist_dec = int(cp.vl["PCM_BUTTONS"]["BTN_AccDistanceDecrease"])
        events.extend(create_button_events(dist_dec, self.distance_dec_prev, {1: ButtonType.gapAdjustCruise}, unpressed_btn=0))
        self.distance_dec_prev = dist_dec

        dist_inc = int(cp.vl["PCM_BUTTONS"]["BTN_AccDistanceIncrease"])
        events.extend(create_button_events(dist_inc, self.distance_inc_prev, {1: ButtonType.gapAdjustCruise}, unpressed_btn=0))
        self.distance_inc_prev = dist_inc

        return events


    @staticmethod
    def get_can_parsers(CP, CP_SP) -> dict[StrEnum, CANParser]:
        messages_bus0 = [
            ("EPS", 100),
            ("CARSPEED", 50),
            ("PEDAL", 50),
            ("EPB", 1),
            ("ACC_EPS_STATE", 50),
            ("DRIVE_STATE", 50),
            ("STALKS", 1),
            ("BCM", 1),
            ("PCM_BUTTONS", 20),
            ("YAW_RATE", 50),
            ("AXAY", 50),
        ]

        messages_bus2 = [
            ("ACC_MPC_STATE", 50),
            ("ACC_HUD_ADAS", 50),
            ("ACC_CMD", 50),
        ]

        return {
            Bus.pt: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus0, CanBus.MAIN),
            Bus.cam: CANParser(DBC[CP.carFingerprint][Bus.pt], messages_bus2, CanBus.CAM),
        }
