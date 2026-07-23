## ============================================================================
## values-tao.py  —— 涛哥版 A2 方案纯复刻 (供对照测试, 部署时改名为 values.py)
## ----------------------------------------------------------------------------
## CarControllerParams = 100% 涛哥原值 (无你自己的 LOCK1~7 / ANTISTALL / allowance=300):
##   STEER_DELTA_UP=7  STEER_DELTA_DOWN=10  STEER_SOFTSTART_STEP=6
##   STEER_DRIVER_ALLOWANCE=68  K_DASHSPEED=0.0719088
##   全部与 byd涛哥版本/values.py 一致。
##
## 平台/DBC/车型/CanBus/LKASConfig/FW_QUERY 保留【你的唐DM 2018】定义 (byd_tang_dm_2018),
##   否则指纹/DBC 对不上会认不出车。只有 CarControllerParams 换成涛哥的。
##
## ⚠️ 一定要和 bydcan-tao.py / carcontroller-tao.py / byd-tao.h 四个一起改名部署,
##    单独换这个会因参数变化(allowance 300->68)改变对抗手感, 需一起测。
##
## ⚠️ 【重要】涛哥参数无你第50章的 allowance=300 保护。allowance=68 时若司机大力反向对抗,
##    OP 可能被 driver 限幅压塌 -> MainTq=0 -> 有触发对抗型锁死的风险(你笔记第50章实证)。
##    这正是 A2 纯涛哥要验证的: 涛哥靠 fake_318 主动伪造 + Config透传, 是否能在 allowance=68
##    下也不锁。务必空旷低速 + 开看门狗抓包测试。
## ============================================================================
from dataclasses import dataclass, field
from enum import IntFlag
from opendbc.car import Bus, DbcDict, PlatformConfig, Platforms, CarSpecs
from opendbc.car.structs import CarParams
from opendbc.car.docs_definitions import CarHarness, CarDocs, CarParts, SupportType
from opendbc.car.fw_query_definitions import FwQueryConfig, Request, StdQueries

Ecu = CarParams.Ecu


class CarControllerParams:
  # ===== 以下全部为涛哥原值 (byd涛哥版本/values.py) =====
  STEER_MAX = 300
  STEER_DELTA_UP = 7
  STEER_DELTA_DOWN = 10

  STEER_DRIVER_ALLOWANCE = 68
  STEER_DRIVER_MULTIPLIER = 3
  STEER_DRIVER_FACTOR = 1
  STEER_ERROR_MAX = 50

  STEER_STEP = 2  # 100/2=50hz
  STEER_SOFTSTART_STEP = 6  # 20ms(50Hz) * 300 / 6 = 1000ms, 软起爬满耗时1秒

  ACC_STEP = 2  # 50hz

  ACCEL_MAX = 2.0
  ACCEL_MIN = -3.5

  K_DASHSPEED = 0.0719088  # 涛哥原值 (你的实测精确值是0.072636, 仅影响仪表显示速度约1%, 与横向测试无关)

  USE_STEERING_SPEED_LIMITER = False

  # op long control (涛哥原值)
  K_accel_jerk_upper = 0.1
  K_accel_jerk_lower = 0.5
  K_jerk_xp =            [   4,   10,   20,   40,   80]  # meters
  K_jerk_base_lower_fp = [-2.3, -1.8, -1.4, -1.0, -0.4]
  K_jerk_base_upper_fp = [ 0.8,  0.7,  0.6,  0.3,  0.2]

  # 跟车距离档位映射 (保留你的, 供 longitudinal_planner 引用, 不破坏纵向; 与横向测试无关)
  GAP_TIME_TABLE = {
    1: 1.0,
    2: 1.4,
    3: 1.8,
    4: 2.3,
  }

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
