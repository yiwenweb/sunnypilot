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
    CAR.BYD_TANG_DM_2018: [{
        85: 8,    # EPB - Electronic parking brake
        287: 5,   # EPS - Steering angle/rate (5-byte message)
        289: 8,   # CARSPEED - Vehicle speed display
        301: 8,   # BCM - Body control (door status)
        307: 8,   # STALKS - Lights/turn signals
        546: 8,   # YAW_RATE - Yaw rate
        547: 8,   # AXAY - Acceleration
        578: 8,   # DRIVE_STATE - Gear/brake
        660: 8,   # BELT - Seatbelt status
        694: 8,   # DATETIME - Date/time
        790: 8,   # ACC_MPC_STATE - LKAS control/status
        792: 8,   # ACC_EPS_STATE - EPS feedback
        813: 8,   # ACC_HUD_ADAS - ACC HUD display
        814: 8,   # ACC_CMD - ACC control command
        815: 8,   # ACC_AEB - AEB control
        834: 8,   # PEDAL - Pedal status
        944: 8,   # PCM_BUTTONS - Cruise buttons
    }],

    # BYD Han EV 2020
    # Pure electric vehicle with additional battery and motor status messages
    # Distinguished from other BYD models by messages 1200 and 1201
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
        790: 8,   # ACC_MPC_STATE
        792: 8,   # ACC_EPS_STATE
        813: 8,   # ACC_HUD_ADAS
        814: 8,   # ACC_CMD
        815: 8,   # ACC_AEB
        834: 8,   # PEDAL
        944: 8,   # PCM_BUTTONS
        # Han EV specific messages (for model differentiation)
        1200: 8,  # BATTERY_STATUS - Battery status (EV only)
        1201: 8,  # MOTOR_STATUS - Motor status (EV only)
    }],

    # BYD Song Plus DM-i 2021
    # Plug-in hybrid with same CAN message IDs as Tang DM 2018
    # Note: Requires FW_VERSIONS for precise model identification
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
        790: 8,   # ACC_MPC_STATE
        792: 8,   # ACC_EPS_STATE
        813: 8,   # ACC_HUD_ADAS
        814: 8,   # ACC_CMD
        815: 8,   # ACC_AEB
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
