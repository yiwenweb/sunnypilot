"""
BYD vehicle constants and configuration definitions.

This module defines constants, enums, and configuration parameters for
BYD vehicle adapters, including car models, control parameters, and
platform configurations.

=== （五）重要安全提醒 ===
1. 仅辅助，不可脱手，随时接管
2. 弯道、雨雪、标线模糊、施工路段慎用/关闭
3. 不识别行人、非机动车、静止障碍物
4. 升级后功能以4S店开通版本为准
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
        STEER_STEP: Steering control period (100Hz = 10ms)
        STEER_MAX: Maximum steering torque (11-bit signed: [-1024, 1023] → 对应物理±5Nm)
        STEER_ERROR_MAX: Maximum steering error (350 = 容错阈值)
        STEER_DELTA_UP: Torque increase rate limit (防止EPS过载)
        STEER_DELTA_DOWN: Torque decrease rate limit (快速回正)
        STEER_DRIVER_ALLOWANCE: Driver torque tolerance (驾驶员对抗容差)
        STEER_DRIVER_MULTIPLIER: Driver torque multiplier (对抗放大系数)
        STEER_DRIVER_FACTOR: Driver torque factor (基础因子)
        STEER_ANGLE_MAX: Maximum steering angle (degrees) - 18款唐DM实测值
        ACCEL_MAX: Maximum acceleration (m/s²)
        ACCEL_MIN: Minimum acceleration (m/s²) - 包含制动减速度
    """

    # ===================== 基础转向控制参数（通用）=====================
    STEER_STEP = 1                # 转向控制周期（100Hz，每10ms发送一次790报文）
    STEER_MAX = 1023              # 最大转向扭矩（11位有符号数，映射到物理±5Nm）
    STEER_ERROR_MAX = 350         # 最大转向误差（容错阈值，超过则退出LKAS）

    # 转向速率限制（防止EPS硬件保护）
    STEER_DELTA_UP = 10           # 扭矩上升速率（默认）
    STEER_DELTA_DOWN = 25         # 扭矩下降速率（默认）

    # 驾驶员扭矩对抗参数（防止强制接管）
    STEER_DRIVER_ALLOWANCE = 80   # 驾驶员转向容差
    STEER_DRIVER_MULTIPLIER = 3   # 驾驶员转向倍数
    STEER_DRIVER_FACTOR = 1       # 驾驶员转向因子

    # 转向角度限制（18款唐DM实测最大转向角）
    STEER_ANGLE_MAX = 94.9        # 最大转向角度（度）

    def __init__(self, CP):
        """初始化车型专属控制参数"""
        # ===================== 纵向加速度限制 =====================
        if CP.flags & BydFlags.RAISED_ACCEL_LIMIT:
            self.ACCEL_MAX = 2.0  # 提升版加速度上限（m/s²）
        else:
            self.ACCEL_MAX = 1.5  # 标准版加速度上限（18款唐DM默认）
        self.ACCEL_MIN = -3.5     # 减速度上限（包含制动，m/s²）

        # ===================== 18款唐DM专属调优 =====================
        if CP.carFingerprint == CAR.BYD_TANG_DM_2018:
            # 适配18款唐DM EPS特性，降低上升速率避免保护
            self.STEER_DELTA_UP = 8
            self.STEER_DELTA_DOWN = 20


class BydFlags(IntFlag):
    """BYD vehicle feature flags (车型特征标志位)."""
    HYBRID = 1      # 混动车型（通用）
    PHEV = 2        # 插电混动（唐DM/宋Plus DM-i）
    EV = 4          # 纯电动（汉EV）

    HAS_RADAR = 8   # 配备毫米波雷达
    HAS_BSM = 16    # 配备盲点监测
    RAISED_ACCEL_LIMIT = 32  # 支持更高加速度限制
    ANGLE_CONTROL = 64       # 角度控制模式（未启用，唐DM用扭矩控制）
    STOCK_ACC = 128          # 使用原厂ACC（未启用，用openpilot纵向）


class BydSafetyFlags(IntFlag):
    """BYD safety flags (安全相关标志位)."""
    ALT_BRAKE = (1 << 8)          # 备用制动逻辑
    STOCK_LONGITUDINAL = (2 << 8) # 使用原厂纵向控制


class CanBus:
    """BYD CAN bus definitions (CAN总线定义).

    Bus layout (18款唐DM实测):
    - Bus 0 (MAIN/PT): 动力总线（EPS/ESP/VCU/BCM，核心控制）
    - Bus 1 (AUX): 辅助总线（雷达/车身控制）
    - Bus 2 (CAM): 摄像头/ACC总线（MPC前视摄像头，panda转发Bus0消息）

    发送规则：
    - 790(ACC_MPC_STATE): 发Bus0 → EPS接收
    - 813/814/815: 发Bus0 → VCU/ESP接收
    - 944(PCM_BUTTONS): 发Bus2 → MPC接收
    """
    MAIN = 0      # 主总线（动力）- EPS/ESP/VCU
    AUX = 1       # 辅助总线（车身/雷达）
    CAM = 2       # 摄像头/ACC总线（MPC）
    PT = 0        # 动力总线别名（兼容openpilot命名）


def dbc_dict(pt, radar=None):
    """Generate DBC dictionary (生成DBC文件映射).

    Args:
        pt: Powertrain DBC file name（动力总线DBC）
        radar: Optional radar DBC file name（雷达DBC，可选）

    Returns:
        Dictionary mapping bus types to DBC file names
    """
    d = {Bus.pt: pt}
    if radar is not None:
        d[Bus.radar] = radar
    return d


@dataclass
class BydCarDocs(CarDocs):
    """BYD vehicle documentation (车型文档配置)."""
    package: str = "All"
    car_parts: CarParts = field(default_factory=CarParts.common([CarHarness.custom]))
    support_type: SupportType = SupportType.COMMUNITY  # 社区适配


@dataclass
class BydPlatformConfig(PlatformConfig):
    """BYD platform configuration base class (平台配置基类)."""
    dbc_dict: dict = field(default_factory=lambda: dbc_dict('byd_tang_dm_2018'))

    def init(self):
        self.flags |= BydFlags.PHEV | BydFlags.HAS_RADAR


class CAR(Platforms):
    """BYD supported vehicle models (支持的BYD车型)."""

    # ===================== 18款唐DM（核心适配车型）=====================
    BYD_TANG_DM_2018 = BydPlatformConfig(
        [BydCarDocs("BYD Tang DM 2018", "ACC + LKAS")],  # 文档描述
        CarSpecs(
            mass=2526.0,      # 整备质量（kg）- 18款唐DM官方数据
            wheelbase=2.82,   # 轴距（m）
            steerRatio=19.0,  # 转向比 - 实测值（旧版本验证）
            centerToFrontRatio=0.44,  # 重心到前轴比例
            tireStiffnessFactor=1.0,  # 轮胎刚度因子（适配转向手感）
        ),
        dbc_dict('byd_tang_dm_2018'),  # 绑定18款唐DM专属DBC
        flags=BydFlags.PHEV | BydFlags.HAS_RADAR,  # 插混+毫米波雷达
    )

    # ===================== 汉EV 2020款 =====================
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

    # ===================== 宋Plus DM-i 2021款 =====================
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


# ===================== 全局配置 =====================
# DBC文件映射（自动生成）
DBC = CAR.create_dbc_map()

# 车型分类集合
PHEV_CAR = {CAR.BYD_TANG_DM_2018, CAR.BYD_SONG_PLUS_DMI_2021}  # 插混车型
EV_CAR = {CAR.BYD_HAN_EV_2020}                                 # 纯电车型
RADAR_CAR = {CAR.BYD_TANG_DM_2018, CAR.BYD_HAN_EV_2020, CAR.BYD_SONG_PLUS_DMI_2021}  # 带雷达车型

# 固件查询配置（UDS诊断）
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
        (Ecu.hybrid, 0x7e2, None),     # 混动控制单元（HCU）
        (Ecu.eps, 0x7a0, None),        # 电动助力转向（EPS）
        (Ecu.fwdCamera, 0x7c4, None),  # 前视摄像头（MPC）
    ],
)

# 方向盘扭矩阈值（脱手检测）- 18款唐DM
# 实车诊断发现 EPS 在非激活状态下扭矩信号有偏移，50 太低导致 steeringPressed 持续为 True
# v4 诊断确认: 低速行驶时手握方向盘扭矩经常超过 100，提高到 150
STEER_THRESHOLD = 150