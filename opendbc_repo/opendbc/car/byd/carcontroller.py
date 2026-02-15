"""
BYD CarController - Vehicle control implementation.

策略: 仅 lat_active 或 long_active 时发送控制帧。
非激活时 100% 透传原厂 MPC 帧（由 fwd_hook tx-sync 保证）。

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
        # EPS 可能需要先看到 LKAS_ReqPrepare=1 若干帧，然后才接受 LKAS_Active=1
        self.lkas_prepare_count = 0
        self.LKAS_PREPARE_FRAMES = 25  # 准备阶段帧数 (25帧 @ 50Hz = 0.5秒)
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

        # === 2. 仅激活时发送控制帧 ===
        # 非激活时完全不发帧, fwd_hook 100% 透传原厂 MPC 帧
        if lat_active or long_active:

            # LKAS 准备阶段状态机
            # EPS 需要先看到 LKAS_ReqPrepare=1 若干帧才接受 LKAS_Active=1
            # 关键: 只有在非刹车状态下实际发出 ReqPrepare 的帧才计数
            if lat_active and not self.lkas_was_active:
                # 刚激活: 开始准备阶段
                self.lkas_prepare_count = 0
            if lat_active and not CS.out.brakePressed:
                # 只有非刹车时才递增准备计数（刹车时发的是空帧，EPS 看不到准备信号）
                self.lkas_prepare_count += 1
            if not lat_active:
                self.lkas_prepare_count = 0
            self.lkas_was_active = lat_active

            # 准备阶段: 发 LKAS_ReqPrepare=1, LKAS_Active=0, LKAS_Output=0
            lkas_preparing = lat_active and (self.lkas_prepare_count <= self.LKAS_PREPARE_FRAMES)
            lkas_ready = lat_active and not lkas_preparing

            # ACC 主开关状态 (用于区分 ACC OFF / ACC ON 待机 / ACC ON 激活)
            acc_on = CS.out.cruiseState.available

            # 790 ACC_MPC_STATE @ 50Hz (匹配原厂 MPC 频率)
            if self.frame % 2 == 0:
                can_sends.append(create_steering_control(
                    self.packer, self.CP,
                    apply_steer if lkas_ready else 0,
                    lkas_preparing,  # req_prepare: 准备阶段发 True
                    lkas_ready,      # active: 准备完成后才激活
                    CC.hudControl,
                    self.lkas_counter,
                ))
                self.lkas_counter = (self.lkas_counter + 1) & 0xF

            # 813/814/815 @ 50Hz
            if self.frame % 2 == 0:
                # 813 ACC_HUD_ADAS
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

                # 814 ACC_CMD
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

                # 815 ACC_AEB (空闲值)
                can_sends.append(self._create_acc_aeb(self.acc_counter))
                self.acc_counter = (self.acc_counter + 1) & 0xF

            # 792 ACC_EPS_STATE 假反馈到 Bus 2 @ 50Hz
            if self.frame % 2 == 0:
                can_sends.append(create_fake_eps_feedback(
                    self.packer,
                    fake_torque=apply_steer if lkas_ready else 0,
                    driver_torque=int(CS.out.steeringTorque),
                    lkas_req_prepare=lkas_preparing,
                    lkas_active=lkas_ready,
                    enabled=True,
                    counter=self.eps_counter,
                ))
                self.eps_counter = (self.eps_counter + 1) & 0xF

            # 944 PCM_BUTTONS 转发到 Bus 2 @ 20Hz
            if self.frame % 5 == 0:
                can_sends.append(self._forward_pcm_buttons(True))
                self.btn_counter = (self.btn_counter + 1) & 0xF

        # === 3. 更新执行器实际值 ===
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
