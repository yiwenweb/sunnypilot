"""
BYD CarController - Vehicle control implementation.

策略: 始终发送 790/813/814/815/792 帧，保持与原厂 MPC 相同的帧频率。
非激活时发送空闲值（匹配原厂 MPC 空闲帧），激活时发送控制值。
这确保 EPS 看到连续的 counter 序列，避免帧切换时的 counter 跳变。

CAN message schedule (匹配原厂 MPC 频率):
- 790 (ACC_MPC_STATE) on Bus 0 @ 50Hz — steering control
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
        self.eps_counter = 0         # 792 counter (0-15)
        self.btn_counter = 0         # 944 counter (0-15)
        self.frame = 0

        # LKAS 准备阶段状态机
        self.lkas_prepare_count = 0
        self.LKAS_PREPARE_FRAMES = 100  # 准备阶段帧数 (100帧 @ 50Hz = 2秒)
        self.lkas_was_active = False

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

        # === 2. LKAS 准备阶段状态机 ===
        if lat_active and not self.lkas_was_active:
            self.lkas_prepare_count = 0
        if lat_active and not CS.out.brakePressed:
            self.lkas_prepare_count += 1
        if not lat_active:
            self.lkas_prepare_count = 0
        self.lkas_was_active = lat_active

        lkas_preparing = lat_active and (self.lkas_prepare_count <= self.LKAS_PREPARE_FRAMES)
        lkas_ready = lat_active and not lkas_preparing

        # ACC 主开关状态
        acc_on = CS.out.cruiseState.available

        # === 3. 始终发送控制帧 (保持 counter 连续) ===
        # 关键改动: 不再仅在 lat_active/long_active 时发帧
        # 原厂 MPC 始终发送 790/813/814/815，OP 也必须始终发送
        # 非激活时发送空闲值，激活时发送控制值
        # 这确保 EPS 看到连续的 counter 序列，不会因 counter 跳变而拒绝帧

        # 790 ACC_MPC_STATE @ 50Hz
        if self.frame % 2 == 0:
            can_sends.append(create_steering_control(
                self.packer, self.CP,
                apply_steer if lkas_ready else 0,
                lkas_preparing,
                lkas_ready,
                CC.hudControl,
                self.lkas_counter,
            ))
            self.lkas_counter = (self.lkas_counter + 1) & 0xF

        # 813/814/815 @ 50Hz
        if self.frame % 2 == 0:
            if long_active and CC.hudControl.setSpeed > 0:
                hud_set_speed = CC.hudControl.setSpeed * 3.6
            else:
                hud_set_speed = CS.out.vEgoCluster * 3.6

            can_sends.append(create_acc_hud(
                self.packer, self.CP, CS,
                set_speed=hud_set_speed,
                has_lead=False,
                set_distance=4,
                acc_on=acc_on,
                lat_active=lat_active,
                long_active=long_active,
                counter=self.acc_counter,
            ))

            can_sends.append(create_acc_cmd(
                self.packer, self.CP, CS,
                mrr_lead_dist=100.0,
                accel=actuators.accel if long_active else 0.0,
                resume_from_standstill=True,
                standstill_state=(CS.out.vEgo < 0.1),
                long_active=long_active,
                acc_on=acc_on,
                lat_active=lat_active,
                counter=self.acc_counter,
            ))

            # 815 ACC_AEB — 不发送，MPC 原厂 815 双向透传，保留 AEB 紧急制动功能
            self.acc_counter = (self.acc_counter + 1) & 0xF

        # 792 ACC_EPS_STATE 假反馈到 Bus 2 @ 50Hz
        if self.frame % 2 == 0:
            can_sends.append(create_fake_eps_feedback(
                self.packer,
                fake_torque=apply_steer if lkas_ready else 0,
                driver_torque=int(CS.out.steeringTorque),
                lkas_req_prepare=lkas_preparing,
                lkas_active=lkas_ready,
                enabled=(lat_active or long_active),
                counter=self.eps_counter,
            ))
            self.eps_counter = (self.eps_counter + 1) & 0xF

        # 944 PCM_BUTTONS 转发到 Bus 2 @ 20Hz
        if self.frame % 5 == 0:
            can_sends.append(self._forward_pcm_buttons(True))
            self.btn_counter = (self.btn_counter + 1) & 0xF

        # === 4. 更新执行器实际值 ===
        new_actuators = actuators.as_builder()
        actual_steer = self.apply_steer_last if (lat_active and self.lkas_prepare_count > self.LKAS_PREPARE_FRAMES) else 0
        new_actuators.torque = float(actual_steer / self.params.STEER_MAX) if self.params.STEER_MAX else 0.0
        new_actuators.torqueOutputCan = int(actual_steer)
        if long_active:
            new_actuators.accel = float(actuators.accel)

        self.frame += 1
        return new_actuators, can_sends

    def _create_acc_aeb(self, counter: int):
        """815 ACC_AEB — 原厂空闲帧"""
        dat = bytearray([0x05, 0x80, 0x02, 0x0f, 0xff, 0xff, 0x00, 0x00])
        dat[6] = (0xF << 4) | (counter & 0xF)
        dat[7] = byd_checksum(dat)
        return (815, bytes(dat), CanBus.PT)

    def _forward_pcm_buttons(self, enabled):
        """944 PCM_BUTTONS → Bus 2"""
        dat = bytearray([0x00, 0xd0, 0xff, 0xff, 0xff, 0xff, 0x00, 0x00])
        if enabled:
            dat[0] = 0x03
            dat[1] = 0xd1
        dat[6] = (self.btn_counter << 4) | 0xF
        dat[7] = byd_checksum(dat)
        return (944, bytes(dat), CanBus.CAM)
