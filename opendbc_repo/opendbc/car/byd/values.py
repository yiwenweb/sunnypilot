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
  # 依据门总0.98健康日志 vs 我们锁死dump 的低速持续扭矩包络实测对比:
  #   0-3km/h: 门总 p50=127 p90=176 max=180; 我们锁死时被旧封顶压到 195 并"持续0.36s" -> 锁死
  #   门总 0-3km/h 连续>=180 最长仅 0.04s (纯瞬时尖峰), 连续>=150 最长 0.68s
  #   我们锁死前 0-3km/h 连续>=195 持续 0.36s, >=180 持续 0.38s  <-- 正是这"低速持续大扭矩"顶爆EPS
  # 结论: 不是峰值高低, 是"持续时间"。低速封顶必须更低, 让高扭矩只能瞬时、不能持续。
  # 新封顶参照门总 0-3km/h 的 p50~p90 (127~176): <=3km/h 封 150, 5km/h 封 170, >=10km/h 放开 300。
  USE_LOWSPEED_TORQUE_LIMIT = True
  LOWSPEED_TQ_BP = [0.83, 1.4, 2.8]      # m/s  (≈3, 5, 10 km/h)
  LOWSPEED_TQ_V  = [150, 170, STEER_MAX]  # |扭矩|上限: <=3km/h封150, 5km/h封170, >=10km/h放开300, 线性

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
  # 兜底机制 (与低速封顶并用): 即便封顶到150, 若 <3km/h 持续高扭矩仍可能累积触发EPS过载。
  # 实测分水岭: 门总 0-3km/h 连续>=150 最长 0.68s 安全, 但连续>=180 仅 0.04s(从不持续);
  # 我们锁死前正是连续>=150 达 0.42s + >=180 达 0.38s。
  # 策略: <3km/h 且 |扭矩|>=140 持续超 0.4s(20帧) -> 强制歇 0.3s(15帧), 重置EPS过载计时器,
  # 确保永不出现门总从不出现的"低速持续高扭矩>0.4s"窗口。
  ANTISTALL_ENABLE = True          # 重新启用: dump实证低速持续扭矩0.36~0.42s即锁死
  ANTISTALL_SPEED = 0.83           # m/s (≈3km/h), 只在极低速守护
  ANTISTALL_TORQUE = 140           # |apply_torque| 视为"持续推", 略低于150封顶以提前介入
  ANTISTALL_TRIGGER_FRAMES = 20    # 50Hz * 0.4s, 持续超此即强制释放(锁死实测0.36~0.42s)
  ANTISTALL_RELEASE_FRAMES = 15    # 50Hz * 0.3s, 扭矩归0以重置EPS过载计时器

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
