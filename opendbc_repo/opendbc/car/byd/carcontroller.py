# BYD车辆控制器 - sunnypilot 0.10.1
# 专为比亚迪18款唐DM及其他BYD车型优化
# 版本: 2026.02 稳定版

from enum import StrEnum

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.lateral import apply_driver_steer_torque_limits
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.byd.values import DBC, CAR, CanBus, CarControllerParams
from opendbc.car.byd import bydcan


class CarController(CarControllerBase):
    """BYD车辆控制器"""

    def __init__(self, dbc_names: dict[StrEnum, str], CP, CP_SP):
        super().__init__(dbc_names, CP, CP_SP)
        self.packer = CANPacker(dbc_names[Bus.pt])
        self.params = CarControllerParams(CP)

        # 控制状态
        self.steer_counter = 0
        self.acc_counter = 0
        self.last_steer_torque = 0

        # LKAS状态
        self.lkas_active_prev = False
        self.lkas_req_prepare = False

    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        """更新控制指令"""
        actuators = CC.actuators
        can_sends = []

        # ========== 转向控制 ==========
        # 计算转向扭矩
        new_steer = int(round(actuators.steer * self.params.STEER_MAX))

        # 应用扭矩限制 (防止突变)
        apply_steer = apply_driver_steer_torque_limits(
            new_steer,
            self.last_steer_torque,
            CS.out.steeringTorque,
            self.params,
        )

        # 判断是否激活转向
        lkas_active = CC.latActive and not CS.out.steeringPressed

        # 准备阶段 (平滑过渡)
        if lkas_active and not self.lkas_active_prev:
            self.lkas_req_prepare = True
        elif not lkas_active:
            self.lkas_req_prepare = False

        # 生成转向控制报文
        can_sends.append(bydcan.create_steering_control(
            self.packer,
            self.CP,
            CS.out,
            apply_steer if lkas_active else 0,
            self.lkas_req_prepare,
            lkas_active,
            CC.hudControl,
            self.steer_counter,
        ))

        # 生成EPS反馈欺骗报文 (防止DTC)
        can_sends.append(bydcan.create_fake_eps_feedback(
            self.packer,
            self.CP,
            CS.out,
            apply_steer if lkas_active else 0,
            self.lkas_req_prepare,
            lkas_active,
            CC.enabled,
            self.steer_counter,
        ))

        self.steer_counter = (self.steer_counter + 1) % 16
        self.last_steer_torque = apply_steer
        self.lkas_active_prev = lkas_active

        # ========== 纵向控制 (ACC) ==========
        if self.CP.openpilotLongitudinalControl:
            # 计算加速度指令
            accel = actuators.accel

            # 限制加速度范围
            accel = max(self.params.ACCEL_MIN, min(self.params.ACCEL_MAX, accel))

            # 获取前车距离 (用于jerk计算)
            lead_dist = 100.0  # 默认值
            if CC_SP.leadOne.status:
                lead_dist = CC_SP.leadOne.dRel

            # 停车状态
            standstill_state = CS.out.standstill and CC.enabled
            resume_from_standstill = CC.enabled and CS.out.standstill and actuators.accel > 0

            # 生成ACC控制报文
            can_sends.append(bydcan.create_acc_cmd(
                self.packer,
                self.CP,
                CS.out,
                lead_dist,
                accel,
                resume_from_standstill,
                standstill_state,
                CC.longActive,
            ))

        self.acc_counter = (self.acc_counter + 1) % 16

        # ========== HUD显示 ==========
        # 更新HUD显示 (设定速度、前车指示等)
        # 这部分由原厂系统处理，openpilot不需要发送

        new_actuators = actuators.as_builder()
        new_actuators.steer = apply_steer / self.params.STEER_MAX
        new_actuators.steerOutputCan = apply_steer

        self.frame += 1
        return new_actuators, can_sends
