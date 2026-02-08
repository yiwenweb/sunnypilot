"""
BYD vehicle constants and configuration definitions.

This module defines constants, enums, and configuration parameters for
BYD vehicle adapters, including car models, control parameters, and
platform configurations.
"""

from dataclasses import dataclass, field
from enum import Enum, IntFlag

from opendbc.car import Bus, CarSpecs, PlatformConfig, Platforms
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.structs import CarParams
from opendbc.car.docs_definitions import CarDocs, CarParts, CarHarness, SupportType
from opendbc.car.fw_query_definitions import FwQueryConfig, Request, StdQueries

Ecu = CarParams.Ecu


class CarControllerParams:
    """BYD vehicle control parameters.
    
    Defines steering control limits and rates for BYD vehicles.
    Parameters are tuned for Tang DM 2018 EPS characteristics.
    
    Attributes:
        STEER_STEP: Steering control period
        STEER_MAX: Maximum steering torque
        STEER_ERROR_MAX: Maximum steering error
        STEER_DELTA_UP: Torque increase rate limit
        STEER_DELTA_DOWN: Torque decrease rate limit
        STEER_DRIVER_ALLOWANCE: Driver torque tolerance
        STEER_DRIVER_MULTIPLIER: Driver torque multiplier
        STEER_DRIVER_FACTOR: Driver torque factor
        STEER_ANGLE_MAX: Maximum steering angle (degrees)
        ACCEL_MAX: Maximum acceleration (m/s²)
        ACCEL_MIN: Minimum acceleration (m/s²)
    """

    # 转向控制参数
    STEER_STEP = 1  # 转向控制周期
    STEER_MAX = 1500  # 最大转向扭矩 (适配唐DM EPS)
    STEER_ERROR_MAX = 350  # 最大转向误差

    # 转向速率限制 (防止EPS过载)
    STEER_DELTA_UP = 10  # 转向扭矩上升速率
    STEER_DELTA_DOWN = 25  # 转向扭矩下降速率

    # 驾驶员扭矩限制参数
    STEER_DRIVER_ALLOWANCE = 80  # 驾驶员转向容差
    STEER_DRIVER_MULTIPLIER = 3  # 驾驶员转向倍数
    STEER_DRIVER_FACTOR = 1  # 驾驶员转向因子

    # 转向角度限制
    STEER_ANGLE_MAX = 94.9  # 最大转向角度 (度)

    def __init__(self, CP):
        # 加速度限制
        if CP.flags & BydFlags.RAISED_ACCEL_LIMIT:
            self.ACCEL_MAX = 2.0  # m/s²
        else:
            self.ACCEL_MAX = 1.5  # m/s²
        self.ACCEL_MIN = -3.5  # m/s²

        # 根据车型调整转向参数
        if CP.carFingerprint == CAR.BYD_TANG_DM_2018:
            # 18款唐DM专属调优
            self.STEER_DELTA_UP = 8
            self.STEER_DELTA_DOWN = 20


class BydFlags(IntFlag):
    """BYD vehicle feature flags."""
    HYBRID = 1      # Hybrid vehicle
    PHEV = 2        # Plug-in hybrid
    EV = 4          # Pure electric

    HAS_RADAR = 8   # Has millimeter wave radar
    HAS_BSM = 16    # Has blind spot monitoring
    RAISED_ACCEL_LIMIT = 32  # Supports higher acceleration
    ANGLE_CONTROL = 64       # Angle control mode
    STOCK_ACC = 128          # Stock ACC


class BydSafetyFlags(IntFlag):
    """BYD safety flags."""
    ALT_BRAKE = (1 << 8)
    STOCK_LONGITUDINAL = (2 << 8)


class CanBus:
    """BYD CAN bus definitions.
    
    Bus layout:
    - Bus 0: Powertrain CAN (EPS, ESP, VCU, BCM)
    - Bus 1: Auxiliary CAN (radar, body)
    - Bus 2: ACC/LKAS CAN (MPC camera, forwarded from Bus 0 by panda)
    
    For sending:
    - ACC_MPC_STATE (790): Send on Bus 0 (to EPS)
    - ACC_EPS_STATE (792) spoof: Send on Bus 2 (to MPC)
    - ACC_CMD (814): Send on Bus 0 (to ESP)
    - ACC_HUD_ADAS (813): Send on Bus 0 (to VCU)
    """
    MAIN = 0      # Main CAN (powertrain) - EPS, ESP, VCU
    AUX = 1       # Auxiliary CAN (body/radar)
    CAM = 2       # Camera/ACC CAN (MPC)
    PT = 0        # Alias for powertrain bus


def dbc_dict(pt, radar=None):
    """Generate DBC dictionary.
    
    Args:
        pt: Powertrain DBC file name
        radar: Optional radar DBC file name
        
    Returns:
        Dictionary mapping bus types to DBC file names
    """
    d = {Bus.pt: pt}
    if radar is not None:
        d[Bus.radar] = radar
    return d


@dataclass
class BydCarDocs(CarDocs):
    """BYD vehicle documentation."""
    package: str = "All"
    car_parts: CarParts = field(default_factory=CarParts.common([CarHarness.custom]))
    support_type: SupportType = SupportType.COMMUNITY


@dataclass
class BydPlatformConfig(PlatformConfig):
    """BYD platform configuration base class."""
    dbc_dict: dict = field(default_factory=lambda: dbc_dict('byd_tang_dm_2018'))

    def init(self):
        self.flags |= BydFlags.PHEV | BydFlags.HAS_RADAR


class CAR(Platforms):
    """BYD supported vehicle models."""

    # BYD Tang DM 2018 - Primary adaptation target
    BYD_TANG_DM_2018 = BydPlatformConfig(
        [BydCarDocs("BYD Tang DM 2018", "ACC + LKAS")],
        CarSpecs(
            mass=2526.0,      # Curb weight (kg) - from old version
            wheelbase=2.82,   # Wheelbase (m)
            steerRatio=19.0,  # Steering ratio - from old version
            centerToFrontRatio=0.44,
            tireStiffnessFactor=1.0,  # from old version
        ),
        dbc_dict('byd_tang_dm_2018'),
        flags=BydFlags.PHEV | BydFlags.HAS_RADAR,
    )

    # BYD Han EV 2020
    BYD_HAN_EV_2020 = BydPlatformConfig(
        [BydCarDocs("BYD Han EV 2020-22", "ACC + LKAS")],
        CarSpecs(
            mass=2150.0,
            wheelbase=2.92,
            steerRatio=14.8,
            centerToFrontRatio=0.44,
            tireStiffnessFactor=0.7,
        ),
        dbc_dict('byd_han_ev_2020'),
        flags=BydFlags.EV | BydFlags.HAS_RADAR | BydFlags.HAS_BSM,
    )

    # BYD Song Plus DM-i 2021
    BYD_SONG_PLUS_DMI_2021 = BydPlatformConfig(
        [BydCarDocs("BYD Song Plus DM-i 2021-23", "ACC + LKAS")],
        CarSpecs(
            mass=1780.0,
            wheelbase=2.765,
            steerRatio=15.1,
            centerToFrontRatio=0.44,
            tireStiffnessFactor=0.7,
        ),
        dbc_dict('byd_song_plus_dmi_2021'),
        flags=BydFlags.PHEV | BydFlags.HAS_RADAR,
    )


# DBC file mapping
DBC = CAR.create_dbc_map()

# Vehicle category sets
PHEV_CAR = {CAR.BYD_TANG_DM_2018, CAR.BYD_SONG_PLUS_DMI_2021}
EV_CAR = {CAR.BYD_HAN_EV_2020}
RADAR_CAR = {CAR.BYD_TANG_DM_2018, CAR.BYD_HAN_EV_2020, CAR.BYD_SONG_PLUS_DMI_2021}

# Firmware query configuration
FW_QUERY_CONFIG = FwQueryConfig(
    requests=[
        Request(
            [StdQueries.SHORT_TESTER_PRESENT_REQUEST, StdQueries.OBD_VERSION_REQUEST],
            [StdQueries.SHORT_TESTER_PRESENT_RESPONSE, StdQueries.OBD_VERSION_RESPONSE],
            whitelist_ecus=[Ecu.engine, Ecu.eps, Ecu.abs, Ecu.fwdCamera, Ecu.fwdRadar, Ecu.hybrid],
            bus=0,
        ),
        Request(
            [StdQueries.TESTER_PRESENT_REQUEST, StdQueries.DEFAULT_DIAGNOSTIC_REQUEST,
             StdQueries.EXTENDED_DIAGNOSTIC_REQUEST, StdQueries.UDS_VERSION_REQUEST],
            [StdQueries.TESTER_PRESENT_RESPONSE, StdQueries.DEFAULT_DIAGNOSTIC_RESPONSE,
             StdQueries.EXTENDED_DIAGNOSTIC_RESPONSE, StdQueries.UDS_VERSION_RESPONSE],
            whitelist_ecus=[Ecu.engine, Ecu.eps, Ecu.abs, Ecu.fwdCamera, Ecu.fwdRadar, Ecu.hybrid],
            bus=0,
        ),
    ],
    extra_ecus=[
        (Ecu.hybrid, 0x7e2, None),     # Hybrid control unit
        (Ecu.eps, 0x7a0, None),        # EPS
        (Ecu.fwdCamera, 0x7c4, None),  # Forward camera
    ],
)

# Steering threshold
STEER_THRESHOLD = 100
