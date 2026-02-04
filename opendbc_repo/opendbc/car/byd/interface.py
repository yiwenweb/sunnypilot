# BYD车辆接口 - sunnypilot 0.10.1
# 专为比亚迪18款唐DM及其他BYD车型优化
# 版本: 2026.02 稳定版

from opendbc.car import Bus, structs, get_safety_config
from opendbc.car.byd.carstate import CarState
from opendbc.car.byd.carcontroller import CarController
from opendbc.car.byd.radar_interface import RadarInterface
from opendbc.car.byd.values import (
    CAR, DBC, BydFlags, BydSafetyFlags, CarControllerParams,
    PHEV_CAR, EV_CAR, RADAR_CAR,
)
from opendbc.car.interfaces import CarInterfaceBase

SteerControlType = structs.CarParams.SteerControlType


class CarInterface(CarInterfaceBase):
    """BYD车辆接口类"""

    CarState = CarState
    CarController = CarController
    RadarInterface = RadarInterface

    @staticmethod
    def get_pid_accel_limits(CP, current_speed, cruise_speed):
        """获取加速度限制"""
        params = CarControllerParams(CP)
        return params.ACCEL_MIN, params.ACCEL_MAX

    @staticmethod
    def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw,
                    alpha_long, is_release, docs) -> structs.CarParams:
        """获取车辆参数"""
        ret.brand = "byd"

        # 安全配置
        ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.allOutput)]

        # 转向控制类型: 扭矩控制
        ret.steerControlType = SteerControlType.torque

        # 配置扭矩调优参数
        CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)

        # 转向执行器延迟
        ret.steerActuatorDelay = 0.12
        ret.steerLimitTimer = 0.4

        # ========== 车型专属参数 ==========
        if candidate == CAR.BYD_TANG_DM_2018:
            # 比亚迪唐DM 2018款专属调优
            ret.lateralTuning.init('pid')
            ret.lateralTuning.pid.kiBP = [0.0]
            ret.lateralTuning.pid.kpBP = [0.0]
            ret.lateralTuning.pid.kpV = [0.5]  # 比例增益
            ret.lateralTuning.pid.kiV = [0.08]  # 积分增益
            ret.lateralTuning.pid.kf = 0.00006  # 前馈增益

            # 唐DM的EPS响应较慢，增加延迟
            ret.steerActuatorDelay = 0.15
            ret.steerLimitTimer = 0.5

            # 标记为PHEV
            ret.flags |= BydFlags.PHEV.value

        elif candidate == CAR.BYD_HAN_EV_2020:
            # 比亚迪汉EV 2020款
            ret.lateralTuning.init('pid')
            ret.lateralTuning.pid.kiBP = [0.0]
            ret.lateralTuning.pid.kpBP = [0.0]
            ret.lateralTuning.pid.kpV = [0.6]
            ret.lateralTuning.pid.kiV = [0.1]
            ret.lateralTuning.pid.kf = 0.00007

            ret.steerActuatorDelay = 0.10
            ret.flags |= BydFlags.EV.value

        elif candidate == CAR.BYD_SONG_PLUS_DMI_2021:
            # 比亚迪宋PLUS DM-i 2021款
            ret.lateralTuning.init('pid')
            ret.lateralTuning.pid.kiBP = [0.0]
            ret.lateralTuning.pid.kpBP = [0.0]
            ret.lateralTuning.pid.kpV = [0.55]
            ret.lateralTuning.pid.kiV = [0.09]
            ret.lateralTuning.pid.kf = 0.00006

            ret.flags |= BydFlags.PHEV.value

        # ========== 通用参数 ==========
        # 重心位置
        ret.centerToFront = ret.wheelbase * 0.44

        # 雷达配置
        ret.radarUnavailable = candidate not in RADAR_CAR

        # 纵向控制
        # BYD车型默认使用原厂ACC，openpilot仅控制横向
        # 如需启用openpilot纵向控制，需要额外硬件支持
        ret.openpilotLongitudinalControl = False

        if not ret.openpilotLongitudinalControl:
            ret.safetyConfigs[0].safetyParam |= BydSafetyFlags.STOCK_LONGITUDINAL.value

        # 最小启用速度 (BYD原厂ACC支持全速域)
        ret.minEnableSpeed = -1.0

        # 停车相关参数
        ret.vEgoStopping = 0.25
        ret.vEgoStarting = 0.25
        ret.stoppingDecelRate = 0.3

        # 混动车型响应更快
        if ret.flags & BydFlags.PHEV.value or ret.flags & BydFlags.EV.value:
            ret.longitudinalActuatorDelay = 0.05

        # 盲点监测
        ret.enableBsm = candidate in RADAR_CAR

        return ret

    @staticmethod
    def _get_params_sp(stock_cp: structs.CarParams, ret, candidate, fingerprint,
                       car_fw, alpha_long, docs):
        """获取sunnypilot专属参数"""
        # 可在此添加sunnypilot特有的参数配置
        return ret

    @staticmethod
    def init(CP, CP_SP, can_recv, can_send):
        """初始化 - 用于禁用ECU等操作"""
        # BYD车型暂不需要禁用ECU
        pass

    @staticmethod
    def deinit(CP, can_recv, can_send):
        """反初始化 - 用于重新启用ECU"""
        pass
