"""
BYD vehicle fingerprint definitions.

This module defines CAN fingerprints for BYD vehicle identification.
Fingerprints are used to automatically detect the vehicle model by
analyzing CAN message IDs present on the bus.

Vehicle Differentiation Strategy:
- BYD_HAN_EV_2020: Distinguished by unique messages 1200 (battery) and 1201 (motor)
- BYD_TANG_DM_2018 vs BYD_SONG_PLUS_DMI_2021: Same CAN IDs, differentiated by FW_VERSIONS

Validation Status:
- Requirement 2.1: All required CAN message IDs included
- Requirement 2.2: Tang DM 2018 unique message IDs defined
- Requirement 2.5: Distinguishable from Han EV; Song Plus requires FW_VERSIONS
"""

from opendbc.car.structs import CarParams
from opendbc.car.byd.values import CAR

Ecu = CarParams.Ecu

# CAN fingerprint definitions
# Format: {CAN_ID: message_length}
# These are messages observed on the CAN bus after vehicle startup

FINGERPRINTS = {
    # BYD Tang DM 2018
    # Based on actual CAN bus capture data
    # Core messages (per design document):
    #   85 (EPB), 287 (EPS), 289 (CARSPEED), 301 (BCM), 307 (STALKS),
    #   546 (YAW_RATE), 578 (DRIVE_STATE), 790 (ACC_MPC_STATE),
    #   792 (ACC_EPS_STATE), 813 (ACC_HUD_ADAS), 814 (ACC_CMD),
    #   834 (PEDAL), 944 (PCM_BUTTONS)
    # BYD Tang DM 2018
    # 必须包含 Bus 0 上所有 < 0x800 的消息 ID，否则 fingerprint 匹配会失败
    # （eliminate_incompatible_cars 会因为未知消息而淘汰候选车型）
    # 数据来源: 实际 CAN 总线抓包 (2025)
    CAR.BYD_TANG_DM_2018: [{
        85: 8,    # EPB
        140: 8,
        269: 8,
        270: 8,
        287: 5,   # EPS (5-byte)
        289: 8,   # CARSPEED
        290: 8,
        291: 8,
        301: 8,   # BCM
        307: 8,   # STALKS
        315: 8,
        464: 8,
        496: 8,
        522: 8,
        523: 8,
        527: 8,
        530: 8,
        536: 8,
        537: 8,
        544: 8,
        546: 8,   # YAW_RATE
        547: 8,   # AXAY
        576: 8,
        577: 8,
        578: 8,   # DRIVE_STATE
        588: 8,
        593: 8,
        596: 8,
        636: 8,
        660: 8,   # BELT
        694: 8,   # DATETIME
        784: 8,
        788: 8,
        790: 8,   # ACC_MPC_STATE (原厂 MPC 发送)
        792: 8,   # ACC_EPS_STATE
        800: 8,
        801: 8,
        802: 8,
        813: 8,   # ACC_HUD_ADAS (原厂 MPC 发送)
        814: 8,   # ACC_CMD (原厂 MPC 发送)
        815: 8,   # ACC_AEB (原厂 MPC 发送)
        833: 8,
        834: 8,   # PEDAL
        836: 8,
        854: 8,
        860: 8,
        916: 8,
        926: 8,
        944: 8,   # PCM_BUTTONS
        948: 8,
        973: 8,
        985: 8,
        1037: 8,
        1040: 8,
        1058: 8,
        1074: 8,
        1104: 8,
        1141: 8,
        1172: 8,
        1178: 8,
        1181: 8,
        1193: 8,
        1208: 8,
        1209: 8,
        1219: 8,
        1224: 8,
        1246: 8,
    }],

    # BYD Han EV 2020
    # Pure electric vehicle with additional battery and motor status messages
    # Distinguished from other BYD models by messages 1200 and 1201
    # BYD Han EV 2020
    # Bus 0 messages only
    CAR.BYD_HAN_EV_2020: [{
        85: 8,    # EPB
        287: 5,   # EPS
        289: 8,   # CARSPEED
        301: 8,   # BCM
        307: 8,   # STALKS
        546: 8,   # YAW_RATE
        547: 8,   # AXAY
        578: 8,   # DRIVE_STATE
        660: 8,   # BELT
        694: 8,   # DATETIME
        834: 8,   # PEDAL
        944: 8,   # PCM_BUTTONS
        # Han EV specific messages (for model differentiation)
        1200: 8,  # BATTERY_STATUS - Battery status (EV only)
        1201: 8,  # MOTOR_STATUS - Motor status (EV only)
    }],

    # BYD Song Plus DM-i 2021
    # Plug-in hybrid with same CAN message IDs as Tang DM 2018
    # Note: Requires FW_VERSIONS for precise model identification
    # BYD Song Plus DM-i 2021
    # Bus 0 messages only
    CAR.BYD_SONG_PLUS_DMI_2021: [{
        85: 8,    # EPB
        287: 5,   # EPS
        289: 8,   # CARSPEED
        301: 8,   # BCM
        307: 8,   # STALKS
        546: 8,   # YAW_RATE
        547: 8,   # AXAY
        578: 8,   # DRIVE_STATE
        660: 8,   # BELT
        694: 8,   # DATETIME
        834: 8,   # PEDAL
        944: 8,   # PCM_BUTTONS
    }],
}

# Firmware version fingerprints (FW_VERSIONS)
# Used for more precise model identification when CAN fingerprints are identical
# Read via UDS diagnostic protocol
#
# Important: BYD_TANG_DM_2018 and BYD_SONG_PLUS_DMI_2021 have identical CAN fingerprints,
#            must rely on FW_VERSIONS for differentiation
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
