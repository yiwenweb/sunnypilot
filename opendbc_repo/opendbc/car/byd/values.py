from dataclasses import dataclass, field
from enum import IntFlag
from opendbc.car import Bus, DbcDict, PlatformConfig, Platforms, CarSpecs
from opendbc.car.structs import CarParams
from opendbc.car.docs_definitions import CarHarness, CarDocs, CarParts, SupportType
from opendbc.car.fw_query_definitions import FwQueryConfig, Request, StdQueries

Ecu = CarParams.Ecu


class CarControllerParams:
  STEER_MAX = 300                 # max steer torque (0.98 confirmed max: 300; 897 triggers TorqueFailed)
  STEER_DELTA_UP = 7              # match 0.98 reference (18 causes too rapid changes)
  STEER_DELTA_DOWN = 10           # match 0.98 reference

  STEER_DRIVER_ALLOWANCE = 68
  STEER_DRIVER_MULTIPLIER = 3
  STEER_DRIVER_FACTOR = 1
  STEER_ERROR_MAX = 50            # match 0.98 reference

  STEER_STEP = 2  # 100/2=50hz
  STEER_SOFTSTART_STEP = 6  # 20ms(50Hz) * 300 / 6 = 1000ms to full torque

  ACC_STEP = 2  # 50hz

  ACCEL_MAX = 2.0
  ACCEL_MIN = -3.5

  K_DASHSPEED = 0.0719088  # convert pulse to kph

  USE_STEERING_SPEED_LIMITER = False

  # --- Anti-stall protection (prevents low-speed EPS TorqueFailed lockup) ---
  # Root cause (confirmed from fault logs): at near-standstill the EPS motor cannot move
  # the wheel, so sustained steer torque with no wheel motion stalls the motor. After a
  # few seconds the BYD EPS asserts TorqueFailed and locks LKAS until restart.
  # Mitigation: when low speed + sustained torque + wheel not moving persists, briefly
  # release torque to reset the EPS stall timer, producing a "push / rest" pulse pattern.
  ANTISTALL_ENABLE = True
  ANTISTALL_SPEED = 2.0           # m/s, only guard below this speed
  ANTISTALL_TORQUE = 40           # |apply_torque| (0..STEER_MAX) considered "pushing hard"
  ANTISTALL_RATE = 5.0            # deg/s, below this the wheel is considered "stuck"
  ANTISTALL_TRIGGER_FRAMES = 75   # 50Hz * 1.5s, stall frames before forcing a release
  ANTISTALL_RELEASE_FRAMES = 30   # 50Hz * 0.6s, torque held at 0 to reset EPS timer

  # op long control
  K_accel_jerk_upper = 0.1
  K_accel_jerk_lower = 0.5
  K_jerk_xp =            [   4,   10,   20,   40,   80]
  K_jerk_base_lower_fp = [-2.3, -1.8, -1.4, -1.0, -0.4]
  K_jerk_base_upper_fp = [ 0.8,  0.7,  0.6,  0.3,  0.2]

  def __init__(self, CP):
    pass


class BydSafetyFlags(IntFlag):
  HAN_TANG_DMEV = 0x1


@dataclass
class BydCarDocs(CarDocs):
  package: str = "All"
  car_parts: CarParts = field(default_factory=CarParts.common([CarHarness.custom]))
  support_type: SupportType = SupportType.COMMUNITY


@dataclass
class BydPlatformConfig(PlatformConfig):
  dbc_dict: DbcDict = field(default_factory=lambda: {Bus.pt: "byd_tang_dm_2018"})


class CAR(Platforms):
  BYD_TANG_DM = BydPlatformConfig(
    [BydCarDocs("BYD TANG DM")],
    CarSpecs(mass=2250., wheelbase=2.820, steerRatio=15.0, centerToFrontRatio=0.44, tireStiffnessFactor=1.0),
  )


class LKASConfig:
  DISABLE = 0
  ALARM = 1
  LKA = 2
  ALARM_AND_LKA = 3


class CanBus:
  ESC = 0
  MRR = 1
  MPC = 2


FW_QUERY_CONFIG = FwQueryConfig(
  requests=[
    Request(
      [StdQueries.MANUFACTURER_SOFTWARE_VERSION_REQUEST],
      [StdQueries.MANUFACTURER_SOFTWARE_VERSION_RESPONSE],
      bus=CanBus.ESC,
    ),
  ],
)

PLATFORM_HANTANG_DMEV = {CAR.BYD_TANG_DM}

MPC_ACC_CAR = {CAR.BYD_TANG_DM}
PT_RADAR_CAR = {CAR.BYD_TANG_DM}
TORQUE_LAT_CAR = {CAR.BYD_TANG_DM}
EXP_LONG_CAR = {CAR.BYD_TANG_DM}

DBC = CAR.create_dbc_map()
