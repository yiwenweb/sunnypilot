# BYD车型指纹定义 - sunnypilot 0.10.1
# 专为比亚迪18款唐DM及其他BYD车型优化
# 版本: 2026.02 稳定版

from opendbc.car.structs import CarParams
from opendbc.car.byd.values import CAR

Ecu = CarParams.Ecu

# CAN指纹定义
# 格式: {CAN_ID: 报文长度}
# 这些是车辆启动后在CAN总线上观察到的报文

FINGERPRINTS = {
    # 比亚迪唐DM 2018款
    # 基于实际CAN总线抓取数据
    CAR.BYD_TANG_DM_2018: [{
        # Bus 0 - 主CAN (动力总成)
        85: 8,    # EPB 电子驻车
        287: 5,   # EPS 转向角度
        289: 8,   # 车速显示
        301: 8,   # BCM 车身控制
        307: 8,   # 灯光/转向灯
        546: 8,   # 横摆角速度
        547: 8,   # 加速度
        578: 8,   # 驾驶状态 (档位/油门/刹车)
        660: 8,   # 安全带
        694: 8,   # 日期时间
        790: 8,   # ACC_MPC_STATE (LKAS控制)
        792: 8,   # ACC_EPS_STATE (EPS反馈)
        813: 8,   # ACC_HUD_ADAS (HUD显示)
        814: 8,   # ACC_CMD (ACC控制指令)
        815: 8,   # ACC_AEB (AEB控制)
        834: 8,   # 踏板状态
        884: 8,   # 雷达MRR
        944: 8,   # PCM按钮
        1048: 8,  # BSD雷达 (盲点监测)
    }],

    # 比亚迪汉EV 2020款
    CAR.BYD_HAN_EV_2020: [{
        85: 8,
        287: 5,
        289: 8,
        301: 8,
        307: 8,
        546: 8,
        547: 8,
        578: 8,
        660: 8,
        694: 8,
        790: 8,
        792: 8,
        813: 8,
        814: 8,
        815: 8,
        834: 8,
        884: 8,
        944: 8,
        1048: 8,
        # 汉EV特有报文
        1200: 8,  # 电池状态
        1201: 8,  # 电机状态
    }],

    # 比亚迪宋PLUS DM-i 2021款
    CAR.BYD_SONG_PLUS_DMI_2021: [{
        85: 8,
        287: 5,
        289: 8,
        301: 8,
        307: 8,
        546: 8,
        547: 8,
        578: 8,
        660: 8,
        694: 8,
        790: 8,
        792: 8,
        813: 8,
        814: 8,
        815: 8,
        834: 8,
        884: 8,
        944: 8,
        1048: 8,
    }],
}

# 固件版本指纹 (用于更精确的车型识别)
FW_VERSIONS = {
    CAR.BYD_TANG_DM_2018: {
        (Ecu.eps, 0x7a0, None): [
            b'BYD-TANG-EPS-2018',
        ],
        (Ecu.fwdCamera, 0x7c4, None): [
            b'BYD-TANG-MPC-2018',
        ],
    },
    CAR.BYD_HAN_EV_2020: {
        (Ecu.eps, 0x7a0, None): [
            b'BYD-HAN-EPS-2020',
        ],
        (Ecu.fwdCamera, 0x7c4, None): [
            b'BYD-HAN-MPC-2020',
        ],
    },
    CAR.BYD_SONG_PLUS_DMI_2021: {
        (Ecu.eps, 0x7a0, None): [
            b'BYD-SONG-EPS-2021',
        ],
        (Ecu.fwdCamera, 0x7c4, None): [
            b'BYD-SONG-MPC-2021',
        ],
    },
}
