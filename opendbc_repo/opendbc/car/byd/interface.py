"""
BYD CarInterface - lateral only, stock longitudinal.
Based on carrotpilot by yysnet.
"""

from opendbc.car import Bus, structs, get_safety_config
from opendbc.car.byd.carstate import CarState
from opendbc.car.byd.carcontroller import CarController
from opendbc.car.byd.radar_interface import RadarInterface
from opendbc.car.interfaces import CarInterfaceBase

SteerControlType = structs.CarParams.SteerControlType


class CarInterface(CarInterfaceBase):
    CarState = CarState
    CarController = CarController
    RadarInterface = RadarInterface

    @staticmethod
    def _get_params(ret: structs.CarParams, candidate, fingerprint, car_fw,
                    alpha_long, is_release, docs) -> structs.CarParams:
        ret.brand = "byd"
        ret.safetyConfigs = [get_safety_config(structs.CarParams.SafetyModel.byd)]

        # Steering: torque control
        ret.steerControlType = SteerControlType.torque
        CarInterfaceBase.configure_torque_tune(candidate, ret.lateralTuning)
        ret.steerActuatorDelay = 0.05
        ret.steerLimitTimer = 0.4
        ret.minSteerSpeed = 0.0

        # Stock longitudinal - MPC handles ACC
        ret.openpilotLongitudinalControl = False
        ret.pcmCruise = True
        ret.radarUnavailable = True

        ret.minEnableSpeed = -1.0
        ret.centerToFront = ret.wheelbase * 0.44

        return ret

    @staticmethod
    def _get_params_sp(stock_cp, ret, candidate, fingerprint, car_fw, alpha_long, docs):
        return ret

    @staticmethod
    def init(CP, CP_SP, can_recv, can_send):
        pass

    @staticmethod
    def deinit(CP, can_recv, can_send):
        pass
