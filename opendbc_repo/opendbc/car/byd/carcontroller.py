"""
BYD CarController - Vehicle control implementation.

核心改动 (参考涛哥 carrotpilot):
1. counter 从原厂 MPC 接续 (首帧读取原厂 counter +1)
2. 等待 EPS 确认 Prepared 才发扭矩 (不再盲等固定帧数)
3. 透传原厂 MPC 信号值 (cam_lkas/cam_acc/cam_adas/esc_eps)
4. 始终发送 790/813/814 保持 counter 连续
5. fake 792 仅激活时发送

CAN message schedule:
- 790 (ACC_MPC_STATE) on Bus 0 @ 50Hz
- 792 (ACC_EPS_STATE) on Bus 2 @ 50Hz (仅激活时)
- 813 (ACC_HUD_ADAS) on Bus 0 @ 50Hz
- 814 (ACC_CMD) on Bus 0 @ 50Hz
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
        self.lkas_counter = 0
        self.acc_counter = 0
        self.eps_counter = 0
        self.btn_counter = 0
        self.frame = 0

        # counter 接续: 首帧从原厂 MPC counter +1 开始
        self.first_start = True

        # LKAS 准备阶段状态机 (等 EPS 确认)
        self.lkas_req_prepare = False
        self.lkas_active = False
        self.lkas_was_active = False
        self.lat_safeoff = False  # 安全退出: 扭矩归零后才完全退出


    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        actuators = CC.actuators
        can_sends = []

        lat_active = CC.latActive
        long_active = CC.longActive

        # === 0. 首帧: 从原厂 MPC counter 接续 ===
        if self.first_start:
            self.lkas_counter = (CS.acc_mpc_state_counter + 1) & 0xF
            self.acc_counter = (CS.acc_cmd_counter + 1) & 0xF
            self.eps_counter = (CS.eps_state_counter + 1) & 0xF
            self.first_start = False

        # === 1. LKAS 状态机 (等 EPS 确认 Prepared) ===
        apply_torque = 0

        if lat_active:
            if self.lkas_active:
                # EPS 已确认 Prepared → 可以发扭矩
                new_steer = int(round(actuators.torque * self.params.STEER_MAX))
                apply_torque = apply_driver_steer_torque_limits(
                    new_steer, self.apply_steer_last,
                    CS.out.steeringTorque, self.params,
                )
            else:
                # 等待 EPS 确认
                if CS.lkas_prepared:
                    # EPS 回复 LKAS_Prepared=1 → 切换到 active
                    self.lkas_active = True
                    self.lkas_req_prepare = False
                    self.lat_safeoff = True
                else:
                    # 发送 ReqPrepare=1，等待 EPS 确认
                    self.lkas_req_prepare = True

        elif self.lat_safeoff:
            # 安全退出: 扭矩归零后才完全退出
            if self.apply_steer_last == 0:
                self.lat_safeoff = False
            apply_torque = apply_driver_steer_torque_limits(
                0, self.apply_steer_last,
                CS.out.steeringTorque, self.params,
            )
        else:
            # 完全非激活
            self.lkas_req_prepare = False
            self.lkas_active = False

        self.apply_steer_last = apply_torque

        # ACC 主开关状态
        acc_on = CS.out.cruiseState.available

        # === 2. 始终发送 790/813/814 (保持 counter 连续) ===
        # 非激活时透传原厂 MPC 值 (只改 counter/checksum)
        # 激活时修改控制字段

        # 790 ACC_MPC_STATE @ 50Hz
        if self.frame % 2 == 0:
            can_sends.append(create_steering_control(
                self.packer, self.CP, CS.cam_lkas,
                apply_torque if self.lkas_active else 0,
                self.lkas_req_prepare,
                self.lkas_active,
                CC.hudControl,
                self.lkas_counter,
            ))
            self.lkas_counter = (self.lkas_counter + 1) & 0xF

        # 813/814 @ 50Hz
        if self.frame % 2 == 0:
            if long_active and CC.hudControl.setSpeed > 0:
                hud_set_speed = CC.hudControl.setSpeed * 3.6
            else:
                hud_set_speed = CS.out.vEgoCluster * 3.6

            can_sends.append(create_acc_hud(
                self.packer, self.CP, CS, CS.cam_adas,
                set_speed=hud_set_speed,
                has_lead=False,
                set_distance=4,
                acc_on=acc_on,
                lat_active=lat_active,
                long_active=long_active,
                counter=self.acc_counter,
            ))

            can_sends.append(create_acc_cmd(
                self.packer, self.CP, CS, CS.cam_acc,
                mrr_lead_dist=100.0,
                accel=actuators.accel if long_active else 0.0,
                resume_from_standstill=True,
                standstill_state=(CS.out.vEgo < 0.1),
                long_active=long_active,
                acc_on=acc_on,
                lat_active=lat_active,
                counter=self.acc_counter,
            ))

            self.acc_counter = (self.acc_counter + 1) & 0xF

        # === 3. fake 792 仅激活时发送 ===
        if self.frame % 2 == 0 and (lat_active or long_active):
            can_sends.append(create_fake_eps_feedback(
                self.packer, CS.esc_eps,
                fake_torque=apply_torque if self.lkas_active else 0,
                lkas_req_prepare=self.lkas_req_prepare,
                lkas_active=self.lkas_active,
                enabled=True,
                counter=self.eps_counter,
            ))
            self.eps_counter = (self.eps_counter + 1) & 0xF

        # === 4. 944 PCM_BUTTONS 转发到 Bus 2 @ 20Hz ===
        if self.frame % 5 == 0:
            can_sends.append(self._forward_pcm_buttons(True))
            self.btn_counter = (self.btn_counter + 1) & 0xF

        # === 5. 更新执行器实际值 ===
        new_actuators = actuators.as_builder()
        actual_steer = self.apply_steer_last if self.lkas_active else 0
        new_actuators.torque = float(actual_steer / self.params.STEER_MAX) if self.params.STEER_MAX else 0.0
        new_actuators.torqueOutputCan = int(actual_steer)
        if long_active:
            new_actuators.accel = float(actuators.accel)

        self.frame += 1
        return new_actuators, can_sends

    def _forward_pcm_buttons(self, enabled):
        """944 PCM_BUTTONS → Bus 2"""
        dat = bytearray([0x00, 0xd0, 0xff, 0xff, 0xff, 0xff, 0x00, 0x00])
        if enabled:
            dat[0] = 0x03
            dat[1] = 0xd1
        dat[6] = (self.btn_counter << 4) | 0xF
        dat[7] = byd_checksum(dat)
        return (944, bytes(dat), CanBus.CAM)
