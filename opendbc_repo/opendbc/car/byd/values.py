"""BYD vehicle constants - minimal, based on carrotpilot."""

from dataclasses import dataclass, field
from enum import IntFlag

from opendbc.car import Bus, CarSpecs, PlatformConfig, Platforms
from opendbc.car.structs import CarParams
from opendbc.car.docs_definitions import CarDocs, CarParts, CarHarness, SupportType
from opendbc.car.fw_query_definitions import FwQueryConfig, Request, StdQueries

Ecu = CarParams.Ecu


class CarControllerParams:
    STEER_MAX = 300
    STEER_DELTA_UP = 7
    STEER_DELTA_DOWN = 10
    STEER_DRIVER_ALLOWANCE = 68
    STEER_DRIVER_MULTIPLIER = 3
    STEER_DRIVER_FACTOR = 1
    STEER_ERROR_MAX = 50
    STEER_STEP = 2   # 100Hz / 2 = 50Hz

    ACCEL_MAX = 2.0
    ACCEL_MIN = -3.5

    def __init__(self, CP):
        pass


class CanBus:
    MAIN = 0   # PT / ESC bus
    AUX = 1
    CAM = 2    # MPC bus
    PT = 0     # alias


@dataclass
class BydCarDocs(CarDocs):
    package: str = "All"
    car_parts: CarParts = field(default_factory=CarParts.common([CarHarness.custom]))
    support_type: SupportType = SupportType.COMMUNITY


@dataclass
class BydPlatformConfig(PlatformConfig):
    dbc_dict: dict = field(default_factory=lambda: {Bus.pt: 'byd_tang_dm_2018'})


class CAR(Platforms):
    BYD_TANG_DM_2018 = BydPlatformConfig(
        [BydCarDocs("BYD Tang DM 2018", "LKAS")],
        CarSpecs(mass=2526.0, wheelbase=2.82, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
        flags=0,
    )


DBC = CAR.create_dbc_map()

STEER_THRESHOLD = 59  # same as carrotpilot

FW_QUERY_CONFIG = FwQueryConfig(
    requests=[
        Request(
            [StdQueries.MANUFACTURER_SOFTWARE_VERSION_REQUEST],
            [StdQueries.MANUFACTURER_SOFTWARE_VERSION_RESPONSE],
            bus=0,
        ),
    ],
)
