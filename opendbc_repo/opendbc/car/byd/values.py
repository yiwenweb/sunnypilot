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

  K_DASHSPEED = 0.072636  # 00000006实测值(中位数,n=29316样本,线性良好,各速度段偏差<0.1%)
                         # 分速度段验证: 10-40km/h=0.072642, 40-70km/h=0.072562
                         # DBC标注0.0735偏高约1.4%。用户反馈车机低3-5km/h已通过实测修正。

  USE_STEERING_SPEED_LIMITER = False

  # --- Anti-stall protection (默认关闭) ---
  # 同上: 真正根因是 LKAS_Config (见 bydcan.py), 非扭矩持续。关闭以恢复满扭矩, 对齐门总。
  # 看门狗会继续监控, 若 Config=1 后仍锁再议。
  ANTISTALL_ENABLE = False
  ANTISTALL_SPEED = 0.83           # m/s (≈3km/h) [保留参数, 未启用]
  ANTISTALL_TORQUE = 140
  ANTISTALL_TRIGGER_FRAMES = 20
  ANTISTALL_RELEASE_FRAMES = 15

  # --- LOCK3: EPS 请求退出横向 (Prepared) -> 快速松手退出 (20260714 已停用, 见下) ---
  # ❌ 已停用 (LOCK3_ENABLE=False)。两轮门总/段56 数据分析证明 LOCK3 的设计前提是错的:
  #  [证据1] 门总 Prepared=1 事件深度分析 (analyze_menmen_prep_deep, 57个事件):
  #    门总遇到 Prepared=1 有 81%(46/57) 【不退出】, 扭矩维持原值继续接管 (最大对抗 drvTq=189
  #    时门总 OPout 全程 63 纹丝不动)。门总退出与否看【司机对抗力度 drvTq】: 退出事件 drvTq_max
  #    中位 156, 未退出事件仅 64。即 Prepared 只是 EPS 的伴随状态位, 不是"退出命令"。
  #  [证据2] 段56 退出时刻分析 (analyze_seg56_exit): 段56 中 lkas_active 掉0 共 49 次, 【全部
  #    49 次 latActive 仍=1】(上层从没要退, latActive 全程 97.4%=1) 且 cru 仍=1(EPS没撤授权)。
  #    即那 49 次横向断续【全是 LOCK3 自作主张退出】造成的(OPout 按16/帧降到0是其退出收尾特征),
  #    与门总(81%不退)完全相反, 正是"低速无车道线横向不连续"的直接根因。
  #  结论: LOCK3"一见Prepared就快速退出"弊大于利。防锁死改由 LOCK6(限时封顶, 从源头不激怒EPS)
  #    + LOCK4(退出等电机卸载) + LOCK5(重接管慢软起) 负责; 横向退出回归 openpilot 标准机制
  #    (上层 latActive / steeringPressed→override 决定, 与门总一致——门总退出也是靠 drvTq 大)。
  # LOCK3 v4 (20260714 重启, 软响应对齐门总): 前版(v3)一见Prepared就"收扭矩+完全退出Active"
  # 造成段56断续, 遂于39章误关(LOCK3_ENABLE=False) -> 段29正常行驶(33km/h)EPS周期性重握手发
  # Prepared, 我们不响应继续硬顶 -> Prepared+MainTq卡(1,0)0.5s -> TorqueFailed锁死。
  # 门总实证(analyze_menmen_prep_response, 57事件, 排除未接管): 门总Prepared持续【中位3帧max6帧】,
  #   从不超7帧就落回; 门总收扭矩延迟中位0帧(Prepared出现时扭矩已≤16); 全量锁死0次。
  #   门总不锁死的根本 = 【Prepared时不硬顶、扭矩收得快 -> EPS满意 -> Prepared很快落回】,
  #   而非"每次退出"(无对抗时70%没完全退出也不锁)。
  # v4软响应: Prepared确认(去抖PREP_HOLD帧)-> 按速率收扭矩到0(每帧-16, 不硬切防LOCK2)但【保持
  #   active不完全退出】; Prepared落回 -> 下帧自动从0慢软起恢复(不断续); 仅当Prepared持续超
  #   FULL_EXIT帧(>门总max6, 判定真退出)才完全退出Active。既解段29锁死(不硬顶)又不致段56断续。
  LOCK3_ENABLE = True
  LOCK3_PREP_HOLD_FRAMES = 2   # Prepared 连续>=此帧才触发收扭矩(去抖, 滤1帧噪声, ~0.04s快响应)
  LOCK3_FULL_EXIT_FRAMES = 8   # Prepared 持续超此帧(>门总max6) 判真退出 -> 完全退出 Active

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
  LOCK5_GIVEUP_MAX_FRAMES = 150     # giveup 超时: 持续放弃超此帧数(~3s)自动清除并重试

  # --- 无车道线辅助 (20260713 新增 -> 20260714 停用) ---
  # ❌ 已停用并从 carcontroller 移除。原实现在低速转弯(角度>15°)时按
  #    hold_torque = sign(steer_angle) * 120 直接赋值(绕过速率限制/softstart), 与方向盘偏角
  #    【同向】输出大扭矩 = 正反馈自锁: 角度越大越同向顶 -> 顶到机械限位死压 120Nm -> EPS 过载
  #    TorqueFailed 锁死(需断电重启)。且与 LOCK5"顶不动收回"互相触发 0.3~0.5s 震荡, 造成低速
  #    控制不连续。违背笔记28~30章结论(低置信度应"衰减输出"而非"按角度开环编造扭矩")。
  # 若将来要做无车道线辅助: 必须是"衰减/限幅模型输出", 经 apply_driver_steer_torque_limits,
  #    且方向为反向小回中, 角度大时减小而非增大力度。详见笔记。
  LANELESS_ASSIST_ENABLE = False    # 永久停用危险实现
  LANELESS_ASSIST_SPEED = 5.5       # [保留参数, 未启用]

  # --- LOCK6: 低速满扭矩"限时封顶" (对齐门总 0.98 实测包络, 默认开启) ---
  # 门总 22万帧实证 (analyze_menmen_deep):
  #  [1] 满扭矩(|out|>=290)连续段中位仅 3 帧(0.06s), 最长 31 帧(0.62s), >=25帧只 1 次
  #      -> 门总允许【瞬间】满扭矩(起步/路口大转向需要), 但几乎从不持续顶 >0.5s。
  #  [2] 低速包络: 10-15km/h max=240 p99=177; 15-20km/h max=180 p99=141 (无满扭矩帧);
  #      0-10km/h 才允许到 300(短暂)。
  #  段56锁死: 我们低速(7km/h)持续 -300 死顶数秒 -> EPS 过载 TorqueFailed。
  # 策略(B, 限时而非砍死上限): 低速时允许瞬间满扭矩, 但 |命令| 持续接近满(>=HI)超过
  #  HOLD_FRAMES 帧, 就把上限回落到 CEIL, 直到 |命令| 自然降到 <LO 才解除封顶。
  #  既保留门总式瞬间大扭矩, 又杜绝段56式持续死顶。仅低速启用(高速本不锁)。
  LOCK6_ENABLE = True
  LOCK6_SPEED = 5.5            # m/s (≈20km/h) 低于此速度才启用限时封顶 (门总低速包络区)
  LOCK6_HI = 260              # |命令|>=此值视为"接近满扭矩"(门总低速 p99~177, 260 留余量给瞬间尖峰)
  LOCK6_LO = 200             # 封顶后 |命令| 自然降到 <此值 才解除封顶
  LOCK6_HOLD_FRAMES = 25     # 接近满扭矩持续超此帧数(~0.5s, 门总最长满扭矩0.62s) -> 触发回落
  LOCK6_CEIL = 200           # 触发后的扭矩上限 (门总 10-20km/h max 180~240 的中段)

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
