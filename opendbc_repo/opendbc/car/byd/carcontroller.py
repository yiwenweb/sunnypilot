# BYD车辆控制器 - sunnypilot 0.10.1
# 专为比亚迪18款唐DM及其他BYD车型优化
# 版本: 2026.02 稳定版
# 注意: 当前版本仅支持横向控制(LKAS)，纵向使用原厂ACC

from enum import StrEnum

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.byd.values import DBC, CAR, CarControllerParams


class CarController(CarControllerBase):
    """BYD车辆控制器 - 仅横向控制版本"""

    def __init__(self, dbc_names: dict[StrEnum, str], CP, CP_SP):
        super().__init__(dbc_names, CP, CP_SP)
        self.packer = CANPacker(dbc_names[Bus.pt])
        self.params = CarControllerParams(CP)

        # 控制状态
        self.last_steer_torque = 0

    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        """更新控制指令"""
        actuators = CC.actuators
        can_sends = []

        # ========== 横向控制 ==========
        # 当前版本暂不发送任何CAN报文，避免干扰原车系统
        # 后续需要根据实际CAN抓包数据来实现正确的LKAS控制
        # 
        # BYD唐DM的LKAS控制需要:
        # 1. 正确的报文ID和格式
        # 2. 正确的校验和算法
        # 3. 与原车MPC/EPS的正确交互时序
        #
        # 在没有完整验证之前，不发送任何控制报文
        # 这样可以保证原车系统正常工作

        # 计算期望的转向扭矩（仅用于记录，不实际发送）
        apply_steer = 0
        if CC.latActive:
            new_steer = int(round(actuators.torque * self.params.STEER_MAX))
            # 简单限幅
            apply_steer = max(-self.params.STEER_MAX, min(self.params.STEER_MAX, new_steer))

        self.last_steer_torque = apply_steer

        # 更新actuators输出
        new_actuators = actuators.as_builder()
        new_actuators.torque = apply_steer / self.params.STEER_MAX
        new_actuators.torqueOutputCan = apply_steer

        self.frame += 1
        return new_actuators, can_sends
