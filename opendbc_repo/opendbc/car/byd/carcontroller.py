"""
BYD CarController - Vehicle control implementation.

Based on old version behavior analysis:
- 790 (ACC_MPC_STATE) on Bus 0 @ 100Hz — steering control
- 813 (ACC_HUD_ADAS) on Bus 0 @ 50Hz — HUD display
- 814 (ACC_CMD) on Bus 0 @ 50Hz — ACC accel command
- 815 (ACC_AEB) on Bus 0 @ 50Hz — AEB control
- 944 (PCM_BUTTONS) on Bus 2 @ 20Hz — button forwarding
"""

from enum import StrEnum

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from numpy import clip
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.byd.bydcan import create_steering_control, create_acc_cmd, create_acc_hud, byd_checksum
from opendbc.car.byd.values import CarControllerParams, CanBus


class CarController(CarControllerBase):
    def __init__(self, dbc_names: dict[StrEnum, str], CP, CP_SP):
        super().__init__(dbc_names, CP, CP_SP)
        self.packer = CANPacker(dbc_names[Bus.pt])
        self.params = CarControllerParams(CP)

        self.apply_steer_last = 0
        self.lkas_counter = 0
        self.acc_counter = 0
        self.btn_counter = 0

    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        actuators = CC.actuators
        can_sends = []

        lat_active = CC.latActive
        long_active = CC.longActive

        # === Lateral control ===
        if lat_active:
            new_steer = int(round(actuators.torque * self.params.STEER_MAX))
            new_steer = clip(new_steer,
                             self.apply_steer_last - self.params.STEER_DELTA_DOWN,
                             self.apply_steer_last + self.params.STEER_DELTA_UP)
            apply_steer = clip(new_steer, -self.params.STEER_MAX, self.params.STEER_MAX)
        else:
            apply_steer = 0
        self.apply_steer_last = apply_steer

        # 790 (ACC_MPC_STATE) on Bus 0 — every frame (100Hz)
        # Old version: ReqPrepare=0 when not active
        lkas_active = lat_active and CS.lkas_prepared
        lkas_req_prepare = lat_active

        can_sends.append(create_steering_control(
            self.packer, self.CP, CS,
            apply_steer if lkas_active else 0,
            lkas_req_prepare,
            lkas_active,
            CC.hudControl,
            self.lkas_counter,
        ))
        self.lkas_counter = (self.lkas_counter + 1) & 0xF

        # === Longitudinal messages — every other frame (50Hz) ===
        if self.frame % 2 == 0:
            # 814 (ACC_CMD) on Bus 0
            can_sends.append(create_acc_cmd(
                self.packer, self.CP, CS,
                mrr_lead_dist=100.0,
                accel=actuators.accel if long_active else 0.0,
                resume_from_standstill=False,
                standstill_state=False,
                long_active=long_active,
                counter=self.acc_counter,
            ))

            # 813 (ACC_HUD_ADAS) on Bus 0
            can_sends.append(create_acc_hud(
                self.packer, self.CP, CS,
                set_speed=CS.cruiseState.speed * 3.6,
                has_lead=False,
                set_distance=3,
                acc_state=3 if CC.enabled else 0,
                enabled=CC.enabled,
                counter=self.acc_counter,
            ))

            # 815 (ACC_AEB) on Bus 0 — raw bytes matching old version
            can_sends.append(self._create_acc_aeb(self.acc_counter))
            self.acc_counter = (self.acc_counter + 1) & 0xF

        # === Forward 944 (PCM_BUTTONS) to Bus 2 — every 5th frame (20Hz) ===
        if self.frame % 5 == 0:
            can_sends.append(self._forward_pcm_buttons())

        # Update actuators
        new_actuators = actuators.as_builder()
        new_actuators.torque = apply_steer / self.params.STEER_MAX if self.params.STEER_MAX else 0
        new_actuators.torqueOutputCan = apply_steer
        if long_active:
            new_actuators.accel = actuators.accel

        self.frame += 1
        return new_actuators, can_sends

    def _create_acc_aeb(self, counter: int):
        """Create ACC_AEB (815) matching old version idle template.
        Old version: 05 80 02 0f ff ff Fx CC
        """
        dat = bytearray([0x05, 0x80, 0x02, 0x0f, 0xff, 0xff, 0x00, 0x00])
        dat[6] = (0xF << 4) | (counter & 0xF)
        dat[7] = byd_checksum(0xAF, dat)
        return (815, bytes(dat), CanBus.PT)

    def _forward_pcm_buttons(self):
        """Forward PCM_BUTTONS (944) to Bus 2 matching old version.
        Old version: 00 d0 ff ff ff ff xF CC
        """
        dat = bytearray([0x00, 0xd0, 0xff, 0xff, 0xff, 0xff, 0x00, 0x00])
        dat[6] = (self.btn_counter << 4) | 0xF
        dat[7] = byd_checksum(0xAF, dat)
        self.btn_counter = (self.btn_counter + 1) & 0xF
        return (944, bytes(dat), CanBus.CAM)
