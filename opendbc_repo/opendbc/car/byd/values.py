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
  # STEER_SOFTSTART_STEP: 重接管后扭矩上限每帧的爬升量。
  # 历史误判: 曾设 300(1帧到顶,等于禁用软起), 以为门总"立即满扭矩接管"。
  # 但 byd_men_reengage_ramp.py 实测门总重接管后是【慢软起】: 每帧步进≈16, 前几帧甚至为0,
  # 大对抗时 6-8 帧才爬到 ~36。300 的瞬间到顶正是 20260703 大对抗重接管锁死的根因之一。
  # 改回 16 (门总实测步进, = STEER_DELTA_UP), 让重接管扭矩每帧+16 渐进。
  STEER_SOFTSTART_STEP = 16

  ACC_STEP = 2  # 50hz

  ACCEL_MAX = 2.0
  ACCEL_MIN = -3.5

  K_DASHSPEED = 0.0719  # DBC验证为0.0735，但用户反馈车机低3-5km/h（如车机92显C3上95）
                         # 下调约2.2%使C3显示更接近车机。若仍有差异，实车标定后再调。
                         # 实车标定方法：C3上运行 byd_speed_diag.py 记录车机→C3对应关系

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

  # --- LOCK4: 退出时等 EPS 电机实际出力(MainTorque)归零再松手 (默认开启) ---
  # 20260702_013051 实证新型锁死 (既非 LOCK1 Cru=0发扭矩, 亦非 LOCK3 Prepared0->1):
  # 司机全程用力对抗方向盘(drvTq -49~-81), 我们接管后 OPtq 快爬到71 与司机对顶, EPS 电机
  # MainTq 也被顶到 47~70。MADS 检测到 override -> latActive 掉0 -> 我们按 LOCK2 把"命令"
  # 平滑降 48->32->16->0(3帧, 这步对的), 但命令到0那帧【同时】把 Active=0 松手, 而此刻 EPS
  # 实际电机 MainTq 仍冻在 47(司机在顶, 电机滞后未跟随命令回落) -> Active 一撤电机还在出力
  # -> EPS 判"授权撤销但电机仍在出力" -> TorqueFailed 锁死。LOCK2 当时能过是因那次 MainTq 跟着
  # 命令一起归0; 本次司机对抗使 MainTq 滞后卡高位, 而退出条件只看"我们的命令"没看"EPS 实际出力"。
  # 修复: 退出收尾保持 Active=1 且命令=0, 直到 EPS MainTorque 也降到阈值以下才干净松手;
  # 设超时上限防止司机持续对抗时无限挂起(超时后仍松手兜底, 此时命令已持续0, MainTq通常已回落)。
  LOCK4_ENABLE = True
  LOCK4_EPS_RELEASE_TQ = 10     # EPS MainTorque 降到 |x|<=此值 视为电机已卸载, 可安全松手
  LOCK4_EXIT_MAX_FRAMES = 30    # 退出收尾最长挂起帧数(~0.6s), 超时强制松手兜底

  # --- LOCK5: 重接管"延迟出力 + 顶不动收回" (对齐门总 0.98, 默认开启) ---
  # byd_men_reengage_ramp.py 实证 (41段, 195次重接管): 门总在 Active 0->1 重新接管后:
  #  (a) 前 3 帧 LKAS_Output 恒=0 (尤其大对抗 |drv|>=60 那 128 次: 帧+0/+1/+2 均值全 0.0),
  #      即先给 EPS 几帧稳定再出力;
  #  (b) 之后每帧 +16 慢软起 (见 STEER_SOFTSTART_STEP);
  #  (c) 大对抗时出力封顶 ~36~44, 不猛涨;
  #  (d) 顶不动就收回: 样例 drv0=-175 out=[0,0,0,16,21,12,0,0,0,0,0,0] —— 门总试出力发现
  #      顶不动(司机扭矩大且 EPS 电机跟不动)立即把命令收回 0 放弃硬顶。
  # 20260703 锁死正因缺此逻辑: 重接管瞬间冲到 -54 持续硬顶司机 -150 对抗 ~1s -> TorqueFailed。
  LOCK5_ENABLE = True
  LOCK5_REENGAGE_DELAY_FRAMES = 3   # 重接管后强制 0 出力的帧数 (门总帧+0~+2 恒0)
  # 顶不动收回: 司机大力对抗 & 我们出力已达一定值但 EPS 电机(MainTorque)顶不上去 且方向盘几乎不动
  LOCK5_FIGHT_DRV_TQ = 100          # 司机扭矩 |drvTq| 超此值视为"大力对抗"
  LOCK5_STUCK_FRAMES = 25           # 对抗且顶不动持续超此帧数(~0.5s) -> 收回放弃硬顶
  LOCK5_STUCK_OUT = 40              # 我们命令 |out| 超此值却顶不动, 才算真硬顶(门总大对抗也压~40)
  LOCK5_STUCK_MAINTQ = 30           # EPS 电机 |MainTorque| 长期低于此值 = 顶不动(电机没能跟上命令)

  # op long control
  K_accel_jerk_upper = 0.1
  K_accel_jerk_lower = 0.5
  K_jerk_xp =            [   4,   10,   20,   40,   80]
  K_jerk_base_lower_fp = [-2.3, -1.8, -1.4, -1.0, -0.4]
  K_jerk_base_upper_fp = [ 0.8,  0.7,  0.6,  0.3,  0.2]
  
  # 跟车距离档位映射（原车4档，对应813 SetDistance值 1-4）
  # time_gap单位：秒，公式 safe_distance = v_ego * time_gap + 5m
  # 实测标定建议：原车ACC各档位实车跟车测量真实距离反推
  GAP_TIME_TABLE = {
    1: 1.0,   # 近距离
    2: 1.4,   # 中近
    3: 1.8,   # 中远（默认）
    4: 2.3,   # 远距离
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
