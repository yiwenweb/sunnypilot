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

  # --- 低速扭矩上限 (默认关闭) ---
  # 历史: 曾以为低速大扭矩持续导致 EPS 锁死, 加了低速封顶。但取证(byd_field_diff)证明
  # 真正根因是 LKAS_Config=3 vs 门总=1 (见 bydcan.py)。门总在低速/对抗/打死方向下满扭矩
  # 也不锁, 说明扭矩大小不是根因。故关闭封顶, 恢复满扭矩力气 (对齐门总"任何情况都有力")。
  USE_LOWSPEED_TORQUE_LIMIT = False
  LOWSPEED_TQ_BP = [0.83, 1.4, 2.8]      # m/s  (≈3, 5, 10 km/h) [保留参数, 未启用]
  LOWSPEED_TQ_V  = [150, 170, STEER_MAX]

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

  # --- Anti-stall protection (默认关闭) ---
  # 同上: 真正根因是 LKAS_Config (见 bydcan.py), 非扭矩持续。关闭以恢复满扭矩, 对齐门总。
  # 看门狗会继续监控, 若 Config=1 后仍锁再议。
  ANTISTALL_ENABLE = False
  ANTISTALL_SPEED = 0.83           # m/s (≈3km/h) [保留参数, 未启用]
  ANTISTALL_TORQUE = 140
  ANTISTALL_TRIGGER_FRAMES = 20
  ANTISTALL_RELEASE_FRAMES = 15

  # --- LOCK3: EPS 请求退出横向 (Prepared 0->1) -> 快速松手退出 (对齐门总 0.98, 默认开启) ---
  # 门总日志实证 (byd_menmen_prep.py, 41段/1621s): LKAS_Prepared 0->1 = EPS 主动请求"结束本次
  # 横向会话"(通常因驾驶员介入方向盘, drvTq 骤变/很大), 之后 0.08~0.14s 内 byte0 -> 0xF8 完全退出。
  # 门总响应: 一见 Prepared 0->1 就 2-3帧内把扭矩收到0, 随后 Active 置0 退出; 全程 Active=0 占比
  # 80%、ReqPrepare=1 占比 0% -> 门总【只快速退出, 从不重握手/硬顶】。
  # 我们锁死那次(20260701)相反: Prepared 0->1 后仍继续发扭矩(76->90)、Active 保持1, 使 Prepared 与
  # MainTq 卡在(1,0)达 0.5s, EPS 等不到 OP 退出 -> TorqueFailed 锁死。故抄门总: 检测 Prepared 上升沿
  # -> 按速率把扭矩快速收0 -> Active=0 干净退出, 不重握手; 待驾驶员松手 EPS 回稳后走正常流程重接管。
  LOCK3_ENABLE = True
  LOCK3_EXIT_FRAMES = 8        # 退出收尾窗口上限(帧, ~0.16s); 门总实测 2-3帧收完扭矩, 给足余量

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
