"""
BYD CarInterface - Vehicle interface implementation.

This module implements the CarInterface class for BYD vehicles, providing
vehicle parameter configuration and initialization routines.

=== （五）重要安全提醒 ===
1. 仅辅助，不可脱手，随时接管
2. 弯道、雨雪、标线模糊、施工路段慎用/关闭
3. 不识别行人、非机动车、静止障碍物
4. 升级后功能以4S店开通版本为准
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
    
    Core Features:
    - 18款唐DM: 扭矩控制（kp=1.0/ki=0.1），支持停车转向，全速域激活
    - 汉EV 2020: PID转向控制，更快的执行器响应
    - 宋Plus DM-i 2021: PID转向控制，适配混动特性
    - 通用配置: pcmCruise=False，openpilot纵向控制，原厂安全限制
    """

    CarState = CarState
    CarController = CarController
    RadarInterface = RadarInterface

    @staticmethod
    def get_pid_accel_limits(CP, current_speed, cruise_speed):
        """Get acceleration limits for PID control.
        
        Returns:
            tuple: (ACCEL_MIN, ACCEL_MAX) from CarControllerParams
        """
        params = CarControllerParams(CP)
        return params.ACCEL_MIN, params.ACCEL_MAX

    @staticmethod
    def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw,
                    alpha_long, is_release, docs) -> structs.CarParams:
        """Configure vehicle parameters (核心参数配置入口).

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

        # ===================== 安全配置（核心）=====================
        # SAFETY_BYD 模式包含：
        # - RX校验: EPS/CARSPEED/DRIVE_STATE/ACC_EPS_STATE/PEDAL/PCM_BUTTONS
        # - TX白名单: 790/813/814/815(Bus0)、944(Bus2)
        # - 转向扭矩限制: max_torque=300，速率限制
        # - 纵向加速度限制: -3.5 ~ +2.0 m/s²
        # - Bus0↔Bus2 消息转发，MADS模式支持
        ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.byd)]

        # ===================== 通用转向配置 =====================
        # 默认扭矩控制（18款唐DM使用），汉EV/宋Plus会覆盖为PID
        ret.steerControlType = SteerControlType.torque

        # 18款唐DM 扭矩调优参数（与旧版本完全一致）
        # 不使用configure_torque_tune，避免自动调整ki/friction
        ret.lateralTuning.init('torque')
        ret.lateralTuning.torque.kp = 1.0
        ret.lateralTuning.torque.ki = 0.1
        ret.lateralTuning.torque.kf = 1.0
        ret.lateralTuning.torque.friction = 0.1
        ret.lateralTuning.torque.latAccelFactor = 1.0
        ret.lateralTuning.torque.latAccelOffset = 0.0
        ret.lateralTuning.torque.steeringAngleDeadzoneDeg = 0.0

        # 转向执行器延迟（18款唐DM: 0.3s，匹配EPS响应特性）
        ret.steerActuatorDelay = 0.3
        ret.steerLimitTimer = 0.5

        # 允许停车时转向（BYD EPS支持0km/h扭矩指令，核心适配点）
        ret.steerAtStandstill = True

        # ===================== 车型专属参数 =====================
        if candidate == CAR.BYD_TANG_DM_2018:
            # 比亚迪唐DM 2018款（插混）
            ret.flags |= BydFlags.PHEV.value

        elif candidate == CAR.BYD_HAN_EV_2020:
            # 比亚迪汉EV 2020款（纯电）- PID转向控制
            ret.lateralTuning.init('pid')
            ret.lateralTuning.pid.kiBP = [0.0]
            ret.lateralTuning.pid.kpBP = [0.0]
            ret.lateralTuning.pid.kpV = [0.6]
            ret.lateralTuning.pid.kiV = [0.1]
            ret.lateralTuning.pid.kf = 0.00007

            ret.steerActuatorDelay = 0.10  # 纯电车型响应更快
            ret.flags |= BydFlags.EV.value

        elif candidate == CAR.BYD_SONG_PLUS_DMI_2021:
            # 比亚迪宋PLUS DM-i 2021款（插混）- PID转向控制
            ret.lateralTuning.init('pid')
            ret.lateralTuning.pid.kiBP = [0.0]
            ret.lateralTuning.pid.kpBP = [0.0]
            ret.lateralTuning.pid.kpV = [0.55]
            ret.lateralTuning.pid.kiV = [0.09]
            ret.lateralTuning.pid.kf = 0.00006

            ret.flags |= BydFlags.PHEV.value

        # ===================== 通用全局参数 =====================
        # 重心位置（BYD车型通用：轮距×0.44）
        ret.centerToFront = ret.wheelbase * 0.44

        # 雷达配置（TODO: 验证RADAR_MRR格式后启用）
        ret.radarUnavailable = True

        # 纵向控制：启用openpilot纵向（需发送813/814/815到Bus0）
        ret.openpilotLongitudinalControl = True

        if not ret.openpilotLongitudinalControl:
            ret.safetyConfigs[0].safetyParam |= 1  # 原厂纵向控制模式

        # 最小启用速度：-1.0 = 全速域（BYD原厂ACC支持0km/h激活）
        ret.minEnableSpeed = -1.0

        # pcmCruise=False: 不依赖原厂PCM巡航状态，通过RES/SET按钮激活
        ret.pcmCruise = False

        # 停车相关参数（匹配旧版本逻辑）
        ret.vEgoStopping = 0.3    # 判定停车的车速阈值（m/s）
        ret.vEgoStarting = 0.5    # 判定起步的车速阈值（m/s）
        ret.stoppingDecelRate = 0.15  # 停车减速率

        # 混动/纯电车型纵向响应更快
        if ret.flags & BydFlags.PHEV.value or ret.flags & BydFlags.EV.value:
            ret.longitudinalActuatorDelay = 0.05

        # 盲点监测（仅带BSM硬件的车型启用）
        ret.enableBsm = bool(ret.flags & BydFlags.HAS_BSM)

        return ret

    @staticmethod
    def _get_params_sp(stock_cp: structs.CarParams, ret, candidate, fingerprint,
                       car_fw, alpha_long, docs):
        """Get sunnypilot-specific parameters.
        
        预留sunnypilot扩展参数配置入口，当前无额外配置
        """
        return ret

    @staticmethod
    def init(CP, CP_SP, can_recv, can_send):
        """Initialize vehicle interface.

        Called when the vehicle interface is first initialized.
        BYD vehicles do not require ECU disabling (无需禁用ECU，即插即用)
        """
        pass

    @staticmethod
    def deinit(CP, can_recv, can_send):
        """Deinitialize vehicle interface.

        Called when the vehicle interface is being shut down.
        """
        pass