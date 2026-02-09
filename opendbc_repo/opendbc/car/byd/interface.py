"""
BYD CarInterface - Vehicle interface implementation.

This module implements the CarInterface class for BYD vehicles, providing
vehicle parameter configuration and initialization routines.
"""

from opendbc.car import Bus, structs, get_safety_config
from opendbc.car.byd.carstate import CarState
from opendbc.car.byd.carcontroller import CarController
from opendbc.car.byd.radar_interface import RadarInterface
from opendbc.car.byd.values import (
    CAR, BydFlags, BydSafetyFlags, CarControllerParams,
    PHEV_CAR, EV_CAR, RADAR_CAR,
)
from opendbc.car.interfaces import CarInterfaceBase

SteerControlType = structs.CarParams.SteerControlType


class CarInterface(CarInterfaceBase):
    """BYD vehicle interface class.

    Provides vehicle parameter configuration and initialization for BYD vehicles.
    Inherits from CarInterfaceBase and implements required static methods.
    """

    CarState = CarState
    CarController = CarController
    RadarInterface = RadarInterface

    @staticmethod
    def get_pid_accel_limits(CP, current_speed, cruise_speed):
        """Get acceleration limits for PID control."""
        params = CarControllerParams(CP)
        return params.ACCEL_MIN, params.ACCEL_MAX

    @staticmethod
    def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw,
                    alpha_long, is_release, docs) -> structs.CarParams:
        """Configure vehicle parameters.

        Args:
            ret: CarParams structure to populate
            candidate: Vehicle candidate (CAR enum value)
            fingerprint: CAN fingerprint dictionary
            car_fw: List of detected ECU firmware versions
            alpha_long: Whether alpha longitudinal control is enabled
            is_release: Whether this is a release build
            docs: Whether generating documentation

        Returns:
            Configured CarParams structure
        """
        ret.brand = "byd"

        # 安全配置 - 使用 SAFETY_BYD 模式
        # byd.h 实现了:
        #   - RX checks: EPS, CARSPEED, DRIVE_STATE, ACC_EPS_STATE, PEDAL, PCM_BUTTONS
        #   - TX whitelist: 790(LKAS), 813(HUD), 814(ACC), 815(AEB) on Bus 0, 944 on Bus 2
        #   - 转向扭矩限制 (max_torque=300, rate limiting)
        #   - 纵向加速度限制 (-3.5 ~ +2.0 m/s²)
        #   - Bus 0 <-> Bus 2 消息转发 (fwd hook)
        #   - MADS 支持 (acc_main_on from PCM_BUTTONS)
        ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.byd)]

        # 转向控制类型: 扭矩控制
        ret.steerControlType = SteerControlType.torque

        # 配置扭矩调优参数 — 手动设置与旧版本完全一致的参数
        # 旧版本: kp=1.0, ki=0.1, kf=1.0, friction=0.1
        # 不使用 configure_torque_tune，因为它会设置 ki=0.3 和从替代车型查表的 friction/latAccelFactor
        ret.lateralTuning.init('torque')
        ret.lateralTuning.torque.kp = 1.0
        ret.lateralTuning.torque.ki = 0.1
        ret.lateralTuning.torque.kf = 1.0
        ret.lateralTuning.torque.friction = 0.1
        ret.lateralTuning.torque.latAccelFactor = 1.0
        ret.lateralTuning.torque.latAccelOffset = 0.0
        ret.lateralTuning.torque.steeringAngleDeadzoneDeg = 0.0

        # 转向执行器延迟 (旧版本: 0.3)
        ret.steerActuatorDelay = 0.3
        ret.steerLimitTimer = 0.5

        # ========== 车型专属参数 ==========
        if candidate == CAR.BYD_TANG_DM_2018:
            # 比亚迪唐DM 2018款
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
        # TODO: 启用雷达后需要验证 RADAR_MRR 消息格式
        ret.radarUnavailable = True

        # 纵向控制 — 旧版本 openpilotLongitudinalControl=True
        # 需要发送 813, 814, 815 到 Bus 0
        ret.openpilotLongitudinalControl = True

        if not ret.openpilotLongitudinalControl:
            ret.safetyConfigs[0].safetyParam |= 1  # BYD_PARAM_STOCK_LONGITUDINAL

        # 最小启用速度 (BYD原厂ACC支持全速域)
        ret.minEnableSpeed = -1.0

        # pcmCruise=False: openpilot 不依赖 PCM 的巡航状态来 engage/disengage。
        # 而是通过按钮事件（RES/SET 按钮释放时触发 buttonEnable）来管理。
        # 这样按 ACC 开关只是 available=True，还需要按 RES/SET 才能真正激活。
        ret.pcmCruise = False

        # 停车相关参数 (from old version)
        ret.vEgoStopping = 0.3
        ret.vEgoStarting = 0.5
        ret.stoppingDecelRate = 0.15

        # 混动车型响应更快
        if ret.flags & BydFlags.PHEV.value or ret.flags & BydFlags.EV.value:
            ret.longitudinalActuatorDelay = 0.05

        # 盲点监测 — 只有带 BSM 硬件的车型才启用
        ret.enableBsm = bool(ret.flags & BydFlags.HAS_BSM)

        return ret

    @staticmethod
    def _get_params_sp(stock_cp: structs.CarParams, ret, candidate, fingerprint,
                       car_fw, alpha_long, docs):
        """Get sunnypilot-specific parameters."""
        # Additional sunnypilot-specific parameter configuration can be added here
        return ret

    @staticmethod
    def init(CP, CP_SP, can_recv, can_send):
        """Initialize vehicle interface.

        Called when the vehicle interface is first initialized.
        BYD vehicles do not require ECU disabling.
        """
        pass

    @staticmethod
    def deinit(CP, can_recv, can_send):
        """Deinitialize vehicle interface.

        Called when the vehicle interface is being shut down.
        """
        pass
