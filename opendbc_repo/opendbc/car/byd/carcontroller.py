"""
BYD CarController - Vehicle lateral control implementation.

Sends ACC_MPC_STATE (790) on Bus 0 to control EPS steering.
LKAS flow: ReqPrepare -> wait Prepared -> Active with torque
"""

from enum import StrEnum

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from numpy import clip
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.byd.bydcan import create_steering_control, byd_checksum
from opendbc.car.byd.values import CarControllerParams, CanBus


class CarController(CarControllerBase):
    def __init__(self, dbc_names: dict[StrEnum, str], CP, CP_SP):
        super().__init__(dbc_names, CP, CP_SP)
        self.packer = CANPacker(dbc_names[Bus.pt])
        self.params = CarControllerParams(CP)

        self.apply_steer_last = 0
        self.steer_rate_counter = 0
        self.lkas_counter = 0

    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        actuators = CC.actuators
        can_sends = []

        # Lateral control
        lat_active = CC.latActive

        # Calculate desired steering torque
        if lat_active:
            new_steer = int(round(actuators.torque * self.params.STEER_MAX))
            # Apply rate limiting
            new_steer = clip(new_steer,
                             self.apply_steer_last - self.params.STEER_DELTA_DOWN,
                             self.apply_steer_last + self.params.STEER_DELTA_UP)
            apply_steer = clip(new_steer, -self.params.STEER_MAX, self.params.STEER_MAX)
        else:
            apply_steer = 0

        self.apply_steer_last = apply_steer

        # Send ACC_MPC_STATE (790) on Bus 0 every frame
        # LKAS state machine: always request prepare, activate when latActive
        lkas_req_prepare = True  # Always request EPS to be ready
        lkas_active = lat_active and CS.lkas_prepared

        can_sends.append(create_steering_control(
            self.packer, self.CP, CS,
            apply_steer if lkas_active else 0,
            lkas_req_prepare,
            lkas_active,
            CC.hudControl,
            self.lkas_counter,
        ))
        self.lkas_counter = (self.lkas_counter + 1) & 0xF

        # Update actuators
        new_actuators = actuators.as_builder()
        new_actuators.torque = apply_steer / self.params.STEER_MAX if self.params.STEER_MAX else 0
        new_actuators.torqueOutputCan = apply_steer

        self.frame += 1
        return new_actuators, can_sends
