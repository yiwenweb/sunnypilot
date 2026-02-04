# BYD车型常量定义 - sunnypilot 0.10.1
# 专为比亚迪18款唐DM及其他BYD车型优化
# 版本: 2026.02 稳定版

from dataclasses import dataclass, field
from enum import Enum, IntFlag

from opendbc.car import Bus, CarSpecs, PlatformConfig, Platforms
from opendbc.car.common.conversions import Conversions as CV
from opendbc.car.structs import CarParams
from opendbc.car.docs_definitions import CarDocs, CarParts, CarHarness, SupportType
from opendbc.car.fw_query_definitions import FwQueryConfig, Request, StdQueries

Ecu = CarParams.Ecu


class CarControllerParams:
    """BYD车辆控制参数 - 针对18款唐DM优化"""

    # 转向控制参数
    STEER_STEP = 1  # 转向控制周期
    STEER_MAX = 1500  # 最大转向扭矩 (适配唐DM EPS)
    STEER_ERROR_MAX = 350  # 最大转向误差

    # 转向速率限制 (防止EPS过载)
    STEER_DELTA_UP = 10  # 转向扭矩上升速率
    STEER_DELTA_DOWN = 25  # 转向扭矩下降速率

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
    """BYD车型特性标志"""
    # 检测到的标志
    HYBRID = 1  # 混动车型
    PHEV = 2  # 插电混动
    EV = 4  # 纯电动

    # 静态标志
    HAS_RADAR = 8  # 有毫米波雷达
    HAS_BSM = 16  # 有盲点监测
    RAISED_ACCEL_LIMIT = 32  # 支持更高加速度
    ANGLE_CONTROL = 64  # 角度控制模式
    STOCK_ACC = 128  # 原厂ACC


class BydSafetyFlags(IntFlag):
    """BYD安全标志"""
    ALT_BRAKE = (1 << 8)
    STOCK_LONGITUDINAL = (2 << 8)


class CanBus:
    """BYD CAN总线定义"""
    MAIN = 0  # 主CAN (动力总成)
    AUX = 1  # 辅助CAN (车身)
    ESC = 0  # ESC/ESP总线
    MPC = 1  # MPC/摄像头总线
    RADAR = 2  # 雷达总线


def dbc_dict(pt, radar=None):
    """生成DBC字典"""
    d = {Bus.pt: pt}
    if radar is not None:
        d[Bus.radar] = radar
    return d


@dataclass
class BydCarDocs(CarDocs):
    """BYD车型文档"""
    package: str = "All"
    car_parts: CarParts = field(default_factory=CarParts.common([CarHarness.custom]))
    support_type: SupportType = SupportType.COMMUNITY


@dataclass
class BydPlatformConfig(PlatformConfig):
    """BYD平台配置基类"""
    dbc_dict: dict = field(default_factory=lambda: dbc_dict('byd_tang_dm_2018'))

    def init(self):
        self.flags |= BydFlags.PHEV | BydFlags.HAS_RADAR


class CAR(Platforms):
    """BYD支持的车型枚举"""

    # 比亚迪唐DM 2018款 - 主要适配车型
    BYD_TANG_DM_2018 = BydPlatformConfig(
        [BydCarDocs("BYD Tang DM 2018", "ACC + LKAS")],
        CarSpecs(
            mass=2390.0,  # 整备质量 kg
            wheelbase=2.82,  # 轴距 m
            steerRatio=15.3,  # 转向比
            centerToFrontRatio=0.44,
            tireStiffnessFactor=0.7,
        ),
        dbc_dict('byd_tang_dm_2018'),
        flags=BydFlags.PHEV | BydFlags.HAS_RADAR,
    )

    # 比亚迪汉EV 2020款
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

    # 比亚迪宋PLUS DM-i 2021款
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


# DBC文件映射
DBC = CAR.create_dbc_map()

# 车型分类集合
PHEV_CAR = {CAR.BYD_TANG_DM_2018, CAR.BYD_SONG_PLUS_DMI_2021}
EV_CAR = {CAR.BYD_HAN_EV_2020}
RADAR_CAR = {CAR.BYD_TANG_DM_2018, CAR.BYD_HAN_EV_2020, CAR.BYD_SONG_PLUS_DMI_2021}

# 固件查询配置
FW_QUERY_CONFIG = FwQueryConfig(
    requests=[
        Request(
            [StdQueries.SHORT_TESTER_PRESENT_REQUEST, StdQueries.OBD_VERSION_REQUEST],
            [StdQueries.SHORT_TESTER_PRESENT_RESPONSE, StdQueries.OBD_VERSION_RESPONSE],
            whitelist_ecus=[Ecu.engine, Ecu.eps, Ecu.abs, Ecu.fwdCamera, Ecu.fwdRadar],
            bus=0,
        ),
        Request(
            [StdQueries.TESTER_PRESENT_REQUEST, StdQueries.DEFAULT_DIAGNOSTIC_REQUEST,
             StdQueries.EXTENDED_DIAGNOSTIC_REQUEST, StdQueries.UDS_VERSION_REQUEST],
            [StdQueries.TESTER_PRESENT_RESPONSE, StdQueries.DEFAULT_DIAGNOSTIC_RESPONSE,
             StdQueries.EXTENDED_DIAGNOSTIC_RESPONSE, StdQueries.UDS_VERSION_RESPONSE],
            whitelist_ecus=[Ecu.engine, Ecu.eps, Ecu.abs, Ecu.fwdCamera, Ecu.fwdRadar],
            bus=0,
        ),
    ],
    extra_ecus=[
        (Ecu.hybrid, 0x7e2, None),  # 混动控制单元
        (Ecu.eps, 0x7a0, None),  # EPS
        (Ecu.fwdCamera, 0x7c4, None),  # 前视摄像头
    ],
)

# 转向阈值
STEER_THRESHOLD = 100
