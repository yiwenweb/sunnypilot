from dataclasses import dataclass, field
from enum import IntFlag
from opendbc.car import Bus, DbcDict, PlatformConfig, Platforms, CarSpecs
from opendbc.car.structs import CarParams
from opendbc.car.docs_definitions import CarHarness, CarDocs, CarParts, SupportType
from opendbc.car.fw_query_definitions import FwQueryConfig, Request, StdQueries

Ecu = CarParams.Ecu


class CarControllerParams:
  STEER_MAX = 300                 # 门总 0.98 confirmed working max; 897 is rejected by EPS (TorqueFailed)
  STEER_DELTA_UP = 16             # 门总 0.98 measured per-frame torque rate (+16); 7 made engagement sluggish
  STEER_DELTA_DOWN = 16           # 门总 0.98 measured per-frame torque rate (-16)

  # --- 低速扭矩上限 (防 EPS 低速过载 TorqueFailed 永久锁死) ---
  # 依据门总 0.98 健康日志实测包络: 0-5km/h 峰值仅 ~195 (满300占比0%),
  # 5-10km/h 才偶尔触及300(5%, 且为瞬时非持续), >=10km/h 才常规放开到满扭。
  # 门总靠"低速封顶"规避锁死(扭矩曲线平滑), 而非 ANTISTALL 的推/歇脉冲。
  # 此前缺这条保护 -> 低速大扭矩把方向盘顶到机械限位、扭矩钉满数秒 -> EPS 锁死。
  USE_LOWSPEED_TORQUE_LIMIT = True
  LOWSPEED_TQ_BP = [1.4, 2.8]        # m/s  (≈5, 10 km/h)
  LOWSPEED_TQ_V  = [195, STEER_MAX]  # 对应 |扭矩| 上限: <=5km/h 封 195, >=10km/h 放开 300, 之间线性

  STEER_DRIVER_ALLOWANCE = 68
  STEER_DRIVER_MULTIPLIER = 3
  STEER_DRIVER_FACTOR = 1
  STEER_ERROR_MAX = 50            # match 0.98 reference

  STEER_STEP = 2  # 100/2=50hz
  STEER_SOFTSTART_STEP = 300  # = STEER_MAX -> reaches full ceiling in 1 frame (soft-start disabled to match 门总 0.98, which engages at full torque immediately)

  ACC_STEP = 2  # 50hz

  ACCEL_MAX = 2.0
  ACCEL_MIN = -3.5

  K_DASHSPEED = 0.0735  # convert pulse to kph (matches panda byd.h UPDATE_VEHICLE_SPEED factor)

  USE_STEERING_SPEED_LIMITER = False

  # --- Anti-stall protection (prevents low-speed EPS TorqueFailed lockup) ---
  # Root cause (confirmed from fault logs): at low speed the lateral controller can wind
  # the wheel toward full lock while torque pins at STEER_MAX for several seconds. The BYD
  # EPS tolerates max torque only briefly; sustained near-max torque trips TorqueFailed
  # (locks LKAS until restart). Confirmed: fault at v=1.5 m/s after the wheel wound to
  # ~176deg with torque held at -300 (max) for a few seconds.
  # Mitigation: when low speed + sustained near-max torque persists, briefly release torque
  # to reset the EPS overload timer, producing a "push / rest" pulse that never lets the
  # EPS see a continuous over-threshold window.
  ANTISTALL_ENABLE = False        # disabled: handshake/torque-authority fix supersedes this
  ANTISTALL_SPEED = 2.0           # m/s, only guard below this speed
  ANTISTALL_TORQUE = 150          # |apply_torque| (0..STEER_MAX) considered "pushing hard"
  ANTISTALL_TRIGGER_FRAMES = 50   # 50Hz * 1.0s, sustained-torque frames before forcing release
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
