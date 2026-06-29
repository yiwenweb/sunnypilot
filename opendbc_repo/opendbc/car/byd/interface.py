from opendbc.car import get_safety_config, structs
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.interfaces import CarInterfaceBase
from opendbc.car.byd.values import CAR, CanBus, BydSafetyFlags, MPC_ACC_CAR, TORQUE_LAT_CAR, EXP_LONG_CAR, \
                                PLATFORM_HANTANG_DMEV
from opendbc.car.byd.carcontroller import CarController
from opendbc.car.byd.carstate import CarState
from opendbc.car.byd.radar_interface import RadarInterface

ButtonType = structs.CarState.ButtonEvent.Type
GearShifter = structs.CarState.GearShifter
TransmissionType = structs.CarParams.TransmissionType
NetworkLocation = structs.CarParams.NetworkLocation

import os
BYD_RADAR = os.getenv("BYD_RADAR") is not None


class CarInterface(CarInterfaceBase):
    CarState = CarState
    CarController = CarController
    RadarInterface = RadarInterface

    @staticmethod
    def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw,
                    alpha_long, is_release, docs) -> structs.CarParams:
        ret.brand = "byd"
        ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.byd)]

        ret.dashcamOnly = False
        if BYD_RADAR:
            ret.radarUnavailable = False
        else:
            ret.radarUnavailable = True

        ret.enableBsm = 0x418 in fingerprint[CanBus.ESC]
        ret.transmissionType = TransmissionType.direct

        ret.minEnableSpeed = -1.
        ret.minSteerSpeed = 0.1 * CV.KPH_TO_MS

        ret.steerActuatorDelay = 0.3   # 门总 0.98 confirmed 0.30 (BYD EPS has ~0.3s lag);
                                       # 0.05 assumed near-instant response → no lead steering → sluggish turn-in
        ret.steerLimitTimer = 0.4

        if candidate in PLATFORM_HANTANG_DMEV:
            ret.safetyConfigs[0].safetyParam |= BydSafetyFlags.HAN_TANG_DMEV.value

        if candidate in MPC_ACC_CAR:
            ret.networkLocation = NetworkLocation.fwdCamera

        use_torque_lat = candidate in TORQUE_LAT_CAR

        if use_torque_lat:
            CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
            # 对齐门总 0.98 实测调参 (configure_torque_tune 默认 ki=0.3, deadzone=0):
            ret.lateralTuning.torque.ki = 0.1                      # 门总=0.1 (默认0.3偏大易振荡)
            ret.lateralTuning.torque.steeringAngleDeadzoneDeg = 0.1  # 门总=0.1
            # 注: kp=1.0/kf=1.0 与门总一致; latAccelFactor/friction 由 override.toml 提供(已对齐2.75/0.1)
        else:
            ret.lateralTuning.init('pid')
            ret.lateralTuning.pid.kpBP, ret.lateralTuning.pid.kiBP = [[8.3, 27.8], [8.3, 27.8]]
            ret.lateralTuning.pid.kpV, ret.lateralTuning.pid.kiV = [[0.6, 0.3], [0.2, 0.1]]
            ret.lateralTuning.pid.kf = 0.000072

        use_experimental_long = candidate in EXP_LONG_CAR

        ret.alphaLongitudinalAvailable = use_experimental_long
        ret.openpilotLongitudinalControl = alpha_long and ret.alphaLongitudinalAvailable
        ret.pcmCruise = True  # Always follow PCM cruise state for activation/speed display, even when OP handles longitudinal accel

        ret.longitudinalTuning.kpBP, ret.longitudinalTuning.kiBP = [[0.], [0.]]
        ret.longitudinalTuning.kpV, ret.longitudinalTuning.kiV = [[1.5], [0.3]]

        if candidate == CAR.BYD_TANG_DM:
            ret.steerRatio = 20.1478  # From closed-source LiveParameters
            ret.minSteerSpeed = 0
            ret.autoResumeSng = True
            ret.startingState = True
            ret.startAccel = 0.8
            ret.stopAccel = -0.5
            ret.vEgoStarting = 0.2 * CV.KPH_TO_MS
            ret.vEgoStopping = 0.1 * CV.KPH_TO_MS
            ret.longitudinalActuatorDelay = 0.5
        else:
            ret.dashcamOnly = True

        return ret

    @staticmethod
    def _get_params_sp(stock_cp: structs.CarParams, ret: structs.CarParamsSP, candidate,
                       fingerprint: dict[int, dict[int, int]], car_fw: list[structs.CarParams.CarFw],
                       alpha_long: bool, docs: bool) -> structs.CarParamsSP:
        return ret

    @staticmethod
    def init(CP, CP_SP, can_recv, can_send):
        pass

    @staticmethod
    def deinit(CP, can_recv, can_send):
        pass
