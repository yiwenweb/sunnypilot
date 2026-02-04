"""
BYD CarController - Vehicle control implementation.

This module implements the CarController class for BYD vehicles.
Current implementation is a "null controller" that does not send any
CAN messages, ensuring no interference with stock ACC/AEB/LKAS systems.

Safety Notes (Requirements 8.1, 8.2, 8.3):
- Does not send any CAN messages that could interfere with stock ACC
- Does not send any CAN messages that could interfere with stock AEB
- Does not send steering control messages until LKAS is fully validated
- Uses stock longitudinal control (STOCK_LONGITUDINAL)
"""

from enum import StrEnum

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.byd.values import CarControllerParams


class CarController(CarControllerBase):
    """BYD vehicle controller - Null controller implementation.
    
    Current Phase (Phase 1): Monitor only, does not send any control messages.
    - Calculates desired torque for debugging and logging
    - Returns empty can_sends list to ensure no interference with stock systems
    - Records control state for future LKAS implementation reference
    
    Safety Guarantees:
    - update() always returns empty can_sends list
    - Does not send any messages that could interfere with ACC/AEB/LKAS
    
    Attributes:
        packer: CAN message packer
        params: Control parameters
        last_steer_torque: Last calculated steering torque (debug)
        apply_steer: Current desired steering torque (debug)
        lat_active: Whether lateral control is active (debug)
        steer_limited: Whether torque was clipped (debug)
    """

    def __init__(self, dbc_names: dict[StrEnum, str], CP, CP_SP):
        """Initialize the CarController.
        
        Args:
            dbc_names: Dictionary mapping bus types to DBC file names
            CP: CarParams structure
            CP_SP: CarParams sunnypilot extension
        """
        super().__init__(dbc_names, CP, CP_SP)
        self.packer = CANPacker(dbc_names[Bus.pt])
        self.params = CarControllerParams(CP)

        # Control state (for debugging)
        self.last_steer_torque = 0
        self.apply_steer = 0
        self.lat_active = False
        self.steer_limited = False

    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        """Update control commands.
        
        Null controller implementation - satisfies Requirements 8.1, 8.2, 8.3:
        - Returns empty can_sends list, does not send any CAN messages
        - Calculates desired torque for debugging, but does not send
        - Records control state for log analysis
        
        Args:
            CC: CarControl control commands
            CC_SP: CarControl sunnypilot extension
            CS: CarState vehicle state
            now_nanos: Current timestamp (nanoseconds)
            
        Returns:
            tuple: (actuators, can_sends)
                - actuators: Updated actuator state
                - can_sends: Empty list (no messages sent)
        """
        actuators = CC.actuators
        
        # Safety: Empty CAN sends list (Requirements 8.1, 8.2, 8.3)
        can_sends = []

        # Lateral control calculation (debug only)
        # Calculate desired steering torque but do not send
        # These values are used for:
        # 1. Debugging and logging
        # 2. Control algorithm validation
        # 3. Future LKAS implementation reference
        
        self.lat_active = CC.latActive
        
        apply_steer = 0
        self.steer_limited = False
        
        if CC.latActive:
            # Convert actuators.torque (-1.0 to 1.0) to actual torque value
            new_steer = int(round(actuators.torque * self.params.STEER_MAX))
            
            # Clip to maximum torque range
            if abs(new_steer) > self.params.STEER_MAX:
                self.steer_limited = True
            apply_steer = max(-self.params.STEER_MAX, min(self.params.STEER_MAX, new_steer))

        # Record control state (for debugging)
        self.apply_steer = apply_steer
        self.last_steer_torque = apply_steer

        # Update actuators output
        # Even without sending CAN messages, update actuators for upper layer logging
        new_actuators = actuators.as_builder()
        new_actuators.torque = apply_steer / self.params.STEER_MAX
        new_actuators.torqueOutputCan = apply_steer

        self.frame += 1
        
        # Return empty can_sends list - core safety guarantee of null controller
        return new_actuators, can_sends
