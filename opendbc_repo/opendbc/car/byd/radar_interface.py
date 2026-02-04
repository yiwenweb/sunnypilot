"""
BYD RadarInterface - Radar data processing implementation.

This module implements the RadarInterface class for BYD vehicles, handling
radar data parsing and target tracking.

Implementation Notes:
- Returns None without errors if radar is unavailable (radarUnavailable=True)
- Parses RADAR_MRR (0x374) message when radar is available
- Handles invalid radar data gracefully without system crashes
"""

from opendbc.can import CANParser
from opendbc.car import Bus, structs
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.byd.values import DBC


def _create_radar_can_parser(car_fingerprint):
    """Create radar CAN parser.
    
    BYD radar messages are defined in the main DBC file (byd_tang_dm_2018.dbc).
    RADAR_MRR (0x374) message contains:
    - TargetID: Target identifier
    - Type: Target type
    - LatDist: Lateral distance (m), scale 0.1, offset -12
    - LongDist: Longitudinal distance (m), scale 1, offset -100
    - IsValid: Target validity flag
    
    Args:
        car_fingerprint: Vehicle fingerprint for DBC selection
        
    Returns:
        CANParser configured for radar messages
    """
    messages = [
        ("RADAR_MRR", 20),  # 20Hz 更新频率
    ]
    # 雷达报文在CAN总线2上
    return CANParser(DBC[car_fingerprint][Bus.pt], messages, 2)


class RadarInterface(RadarInterfaceBase):
    """BYD radar interface class.
    
    Handles radar data parsing and target tracking for BYD vehicles.
    
    Implementation Requirements:
    - Req 9.1: Returns None without errors if radar CAN bus unavailable
    - Req 9.2: Parses RADAR_MRR message for longitudinal and lateral distance
    - Req 9.4: Does not crash when radar data is unavailable
    - Req 9.5: Sets radarUnavailable appropriately based on vehicle config
    
    Attributes:
        pts: Dictionary of tracked radar points
        track_id: Counter for assigning track IDs
        trigger_msg: Message ID that triggers updates (0x374)
        rcp: CAN parser for radar messages (None if radar unavailable)
        updated_messages: Set of recently updated message IDs
    """

    def __init__(self, CP, CP_SP):
        """Initialize RadarInterface.
        
        Args:
            CP: CarParams structure
            CP_SP: CarParams sunnypilot extension
        """
        super().__init__(CP, CP_SP)

        self.pts: dict[int, structs.RadarData.RadarPoint] = {}
        self.track_id = 0
        self.trigger_msg = 0x374  # RADAR_MRR message ID

        # Initialize parser based on radarUnavailable flag
        # Set in CarInterface._get_params based on vehicle model
        if CP.radarUnavailable:
            self.rcp = None
        else:
            self.rcp = _create_radar_can_parser(CP.carFingerprint)

        self.updated_messages = set()

    def update(self, can_strings) -> structs.RadarDataT | None:
        """Update radar data.
        
        Args:
            can_strings: CAN message data
            
        Returns:
            RadarData if radar available, None otherwise
        """
        # Req 9.1: Return None without errors if radar unavailable
        if self.rcp is None:
            return super().update(None)

        # Update CAN parser
        vls = self.rcp.update(can_strings)
        self.updated_messages.update(vls)

        # Wait for trigger message
        if self.trigger_msg not in self.updated_messages:
            return None

        # Process update
        ret = self._update(self.updated_messages)
        self.updated_messages.clear()

        return ret

    def _update(self, updated_messages) -> structs.RadarData:
        """Internal update method - parse radar messages.
        
        Args:
            updated_messages: Set of updated message IDs
            
        Returns:
            Parsed RadarData structure
        """
        ret = structs.RadarData()

        # Check CAN validity
        if not self.rcp.can_valid:
            ret.errors.canError = True
            return ret

        # Parse RADAR_MRR message (Req 9.2)
        rr = self.rcp.vl["RADAR_MRR"]

        # Get target ID for tracking
        target_id = int(rr["TargetID"])

        # Check target validity
        if rr["IsValid"] == 1:
            # Create or update radar point
            if target_id not in self.pts:
                self.pts[target_id] = structs.RadarData.RadarPoint()
                self.pts[target_id].trackId = self.track_id
                self.track_id += 1

            pt = self.pts[target_id]

            # Longitudinal distance (meters) - measured from front of vehicle
            pt.dRel = float(rr["LongDist"])

            # Lateral distance (meters) - vehicle Y-axis, left is positive
            # Note: Negate per sunnypilot convention (left is positive)
            pt.yRel = -float(rr["LatDist"])

            # Relative velocity (m/s) - not available in RADAR_MRR
            pt.vRel = 0.0

            # Relative acceleration and lateral velocity - not available
            pt.aRel = float('nan')
            pt.yvRel = float('nan')

            # Mark as valid measurement
            pt.measured = True
        else:
            # Remove invalid target from tracking list
            if target_id in self.pts:
                del self.pts[target_id]

        ret.points = list(self.pts.values())

        return ret
