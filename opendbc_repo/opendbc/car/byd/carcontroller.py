"""
BYD CarController - Vehicle control implementation.

CAN message schedule:
- 790 (ACC_MPC_STATE) on Bus 0 @ 100Hz — steering control
- 792 (ACC_EPS_STATE) on Bus 2 @ 50Hz — fake EPS feedback to MPC
- 813 (ACC_HUD_ADAS) on Bus 0 @ 50Hz — HUD display
- 814 (ACC_CMD) on Bus 0 @ 50Hz — ACC accel command
- 815 (ACC_AEB) on Bus 0 @ 50Hz — AEB control
- 944 (PCM_BUTTONS) on Bus 2 @ 20Hz — button forwarding
"""

from enum import StrEnum

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.lateral import apply_driver_steer_torque_limits
from opendbc.car.byd.bydcan import (
    create_steering_control, create_acc_cmd, create_acc_hud,
    create_fake_eps_feedback, byd_checksum,
)
from opendbc.car.byd.values import CarControllerParams, CanBus


class CarController(CarControllerBase):
    def __init__(self, dbc_names: dict[StrEnum, str], CP, CP_SP):
        super().__init__(dbc_names, CP, CP_SP)
        self.packer = CANPacker(dbc_names[Bus.pt])
        self.params = CarControllerParams(CP)

        self.apply_steer_last = 0
        self.lkas_counter = 0        # 790 counter (0-15)
        self.acc_counter = 0         # 813/814/815 counter (0-15)
        self.btn_counter = 0         # 944 counter (0-15)
        self.frame = 0

    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        actuators = CC.actuators
        can_sends = []

        lat_active = CC.latActive
        long_active = CC.longActive

        # === 1. 横向控制扭矩计算 ===
        if lat_active:
            new_steer = int(round(actuators.torque * self.params.STEER_MAX))
            apply_steer = apply_driver_steer_torque_limits(
                new_steer, self.apply_steer_last,
                CS.out.steeringTorque, self.params,
            )
        else:
            apply_steer = 0
        self.apply_steer_last = apply_steer

        # === 2. 790 ACC_MPC_STATE — 转向控制 @ 100Hz ===
        # latActive 或 longActive 时发送（EPS 需要看到完整 ACC 报文组）
        if lat_active or long_active:
            can_sends.append(create_steering_control(
                self.packer, self.CP,
                apply_steer if lat_active else 0,
                False,  # req_prepare
                lat_active,
                CS.out.brakePressed,
                CC.hudControl,
                self.lkas_counter,
            ))
            self.lkas_counter = (self.lkas_counter + 1) & 0xF

        # === 3. 813/814/815 纵向控制 @ 50Hz ===
        # EPS 需要完整的 ACC 报文组才会回复 LKAS_Prepared=1
        if lat_active or long_active:
            if self.frame % 2 == 0:
                # 813 ACC_HUD_ADAS
                if long_active and CC.hudControl.setSpeed > 0:
                    hud_set_speed = CC.hudControl.setSpeed * 3.6  # m/s → km/h
                else:
                    hud_set_speed = CS.out.vEgoCluster * 3.6

                can_sends.append(create_acc_hud(
                    self.packer, self.CP, CS,
                    set_speed=hud_set_speed,
                    has_lead=False,
                    set_distance=4,
                    acc_state=1,
                    enabled=True,
                    counter=self.acc_counter,
                ))

                # 814 ACC_CMD
                can_sends.append(create_acc_cmd(
                    self.packer, self.CP, CS,
                    mrr_lead_dist=100.0,
                    accel=actuators.accel if long_active else 0.0,
                    resume_from_standstill=True,
                    standstill_state=(CS.out.vEgo < 0.1),
                    long_active=long_active,
                    counter=self.acc_counter,
                ))

                # 815 ACC_AEB (空闲值)
                can_sends.append(self._create_acc_aeb(self.acc_counter))
                self.acc_counter = (self.acc_counter + 1) & 0xF

        # === 4. 792 ACC_EPS_STATE 假反馈到 Bus 2 @ 50Hz ===
        # 欺骗原厂 MPC，防止 DTC 故障码，保持 AEB 等安全功能正常
        if lat_active or long_active:
            if self.frame % 2 == 0:
                can_sends.append(create_fake_eps_feedback(
                    self.packer,
                    fake_torque=apply_steer if lat_active else 0,
                    driver_torque=int(CS.out.steeringTorque),
                    lkas_req_prepare=False,
                    lkas_active=lat_active,
                    enabled=True,
                ))

        # === 5. 944 PCM_BUTTONS 转发到 Bus 2 @ 20Hz ===
        if lat_active or long_active:
            if self.frame % 5 == 0:
                can_sends.append(self._forward_pcm_buttons(True))
                self.btn_counter = (self.btn_counter + 1) & 0xF

        # === 6. 更新执行器实际值 ===
        new_actuators = actuators.as_builder()
        new_actuators.torque = float(self.apply_steer_last / self.params.STEER_MAX) if self.params.STEER_MAX else 0.0
        new_actuators.torqueOutputCan = int(self.apply_steer_last)
        if long_active:
            new_actuators.accel = float(actuators.accel)

        self.frame += 1
        return new_actuators, can_sends

    def _create_acc_aeb(self, counter: int):
        """生成 ACC_AEB (815) 空闲报文"""
        dat = bytearray([0x05, 0x80, 0x02, 0x0f, 0xff, 0xff, 0x00, 0x00])
        dat[6] = (0xF << 4) | (counter & 0xF)
        dat[7] = byd_checksum(dat)
        return (815, bytes(dat), CanBus.PT)

    def _forward_pcm_buttons(self, enabled):
        """转发 PCM_BUTTONS (944) 到 Bus 2"""
        dat = bytearray([0x00, 0xd0, 0xff, 0xff, 0xff, 0xff, 0x00, 0x00])
        if enabled:
            dat[0] = 0x03
            dat[1] = 0xd1
        dat[6] = (self.btn_counter << 4) | 0xF
        dat[7] = byd_checksum(dat)
        return (944, bytes(dat), CanBus.CAM)