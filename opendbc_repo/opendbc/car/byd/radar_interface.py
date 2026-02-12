"""
BYD RadarInterface - Radar data processing implementation.

This module implements the RadarInterface class for BYD vehicles, handling
radar data parsing and target tracking.

=== （五）重要安全提醒 ===
1. 仅辅助，不可脱手，随时接管
2. 弯道、雨雪、标线模糊、施工路段慎用/关闭
3. 不识别行人、非机动车、静止障碍物
4. 升级后功能以4S店开通版本为准

Implementation Notes:
- Returns None without errors if radar is unavailable (radarUnavailable=True)
- Parses RADAR_MRR (0x374) message when radar is available (18款唐DM毫米波雷达报文)
- Handles invalid radar data gracefully without system crashes
- Radar messages for Tang DM 2018: RADAR_MRR (0x374) on CAN Bus 2, 20Hz update rate
- Supports new fields from updated DBC: TargetSpeed/TargetAccel/Confidence/Type
"""

from opendbc.can import CANParser
from opendbc.car import Bus, structs
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.byd.values import DBC
import math


def _create_radar_can_parser(car_fingerprint):
    """Create radar CAN parser (创建雷达CAN解析器).
    
    BYD radar messages are defined in the main DBC file (byd_tang_dm_2018.dbc).
    RADAR_MRR (0x374) message details (18款唐DM实测，适配更新后的DBC):
    - TargetID: Target identifier (0-255，目标ID，扩展为8位)
    - Type: Target type (0=无目标,1=乘用车,2=货车,3=非机动车)
    - LatDist: Lateral distance (m), scale 0.1, offset -12 → 物理范围: -12~13.5m
    - LongDist: Longitudinal distance (m), scale 1, offset -100 → 物理范围: -100~307m
    - IsValid: Target validity flag (1=valid, 0=invalid)
    - TargetSpeed: Relative speed (km/h), scale 0.05, offset -128 → 物理范围: -128~127.95km/h
    - TargetAccel: Relative acceleration (m/s²), scale 0.1, offset -10 → 物理范围: -10~15.5m/s²
    - Confidence: Target confidence (0=低,1=中,2=高,3=极高)
    
    Args:
        car_fingerprint: Vehicle fingerprint for DBC selection
        
    Returns:
        CANParser configured for radar messages
    """
    messages = [
        ("RADAR_MRR", 20),  # 雷达报文更新频率：20Hz（每50ms一次）
    ]
    # 18款唐DM雷达报文在CAN总线2（CAM总线）上，由panda转发
    return CANParser(DBC[car_fingerprint][Bus.pt], messages, 2)


class RadarInterface(RadarInterfaceBase):
    """BYD radar interface class (比亚迪雷达接口类).
    
    Handles radar data parsing and target tracking for BYD vehicles.
    核心逻辑：
    1. radarUnavailable=True时返回None（不报错）
    2. 解析RADAR_MRR (0x374) 报文提取目标距离/速度/加速度/类型/置信度
    3. 无效目标自动从跟踪列表删除，避免内存泄漏
    4. 所有字段均从雷达报文解析，不再使用默认值
    
    Implementation Requirements:
    - Req 9.1: Returns None without errors if radar CAN bus unavailable
    - Req 9.2: Parses RADAR_MRR message for full radar data (distance/speed/accel)
    - Req 9.4: Does not crash when radar data is unavailable
    - Req 9.5: Sets radarUnavailable appropriately based on vehicle config
    
    Attributes:
        pts: Dictionary of tracked radar points (目标跟踪字典，key=TargetID)
        track_id: Counter for assigning track IDs (全局跟踪ID计数器)
        trigger_msg: Message ID that triggers updates (0x374 = RADAR_MRR)
        rcp: CAN parser for radar messages (None if radar unavailable)
        updated_messages: Set of recently updated message IDs
    """

    def __init__(self, CP, CP_SP):
        """Initialize RadarInterface.
        
        Args:
            CP: CarParams structure (车辆参数，包含radarUnavailable标志)
            CP_SP: CarParams sunnypilot extension
        """
        super().__init__(CP, CP_SP)

        self.pts: dict[int, structs.RadarData.RadarPoint] = {}
        self.track_id = 0
        self.trigger_msg = 0x374  # RADAR_MRR message ID（触发更新的报文ID）

        # Initialize parser based on radarUnavailable flag
        # 18款唐DM启用雷达（radarUnavailable=False），使用更新后的DBC解析
        if CP.radarUnavailable:
            self.rcp = None
        else:
            self.rcp = _create_radar_can_parser(CP.carFingerprint)

        self.updated_messages = set()

    def update(self, can_strings) -> structs.RadarDataT | None:
        """Update radar data (更新雷达数据).
        
        Args:
            can_strings: CAN message data (CAN原始报文数据)
            
        Returns:
            RadarData if radar available, None otherwise
            雷达可用时返回解析后的RadarData，不可用时返回None（不抛出异常）
        """
        # Req 9.1: Return None without errors if radar unavailable
        if self.rcp is None:
            return super().update(None)

        # Update CAN parser（更新CAN解析器，解析新报文）
        vls = self.rcp.update(can_strings)
        self.updated_messages.update(vls)

        # Wait for trigger message（等待触发报文0x374更新）
        if self.trigger_msg not in self.updated_messages:
            return None

        # Process update（处理雷达数据更新）
        ret = self._update(self.updated_messages)
        self.updated_messages.clear()

        return ret

    def _update(self, updated_messages) -> structs.RadarData:
        """Internal update method - parse radar messages (内部解析方法).
        
        Args:
            updated_messages: Set of updated message IDs
            
        Returns:
            Parsed RadarData structure（解析后的雷达数据结构）
        """
        ret = structs.RadarData()

        # Check CAN validity（检查CAN总线有效性）
        if not self.rcp.can_valid:
            ret.errors.canError = True
            return ret

        try:
            # Parse RADAR_MRR message (Req 9.2)（解析核心雷达报文）
            rr = self.rcp.vl["RADAR_MRR"]

            # Get target ID for tracking（获取目标ID用于跟踪）
            target_id = int(rr["TargetID"])

            # Check target validity（检查目标有效性）
            if rr["IsValid"] == 1:
                # Create or update radar point（创建/更新雷达目标点）
                if target_id not in self.pts:
                    self.pts[target_id] = structs.RadarData.RadarPoint()
                    self.pts[target_id].trackId = self.track_id
                    self.track_id += 1  # 全局ID自增，避免重复

                pt = self.pts[target_id]

                # 1. Longitudinal distance (meters) - 纵向距离（米）
                # 车辆前方为正，后方为负
                pt.dRel = float(rr["LongDist"])

                # 2. Lateral distance (meters) - 横向距离（米）
                # 按sunnypilot规范，左侧为正，因此对原始值取反
                pt.yRel = -float(rr["LatDist"])

                # 3. Relative velocity (m/s) - 相对速度（米/秒）
                # 原始值为km/h，转换为m/s（×0.277778），接近车辆为负，远离为正
                pt.vRel = float(rr["TargetSpeed"]) * 0.277778

                # 4. Relative acceleration (m/s²) - 相对加速度（米/平方秒）
                pt.aRel = float(rr["TargetAccel"])

                # 5. Target type - 目标类型
                pt.type = int(rr["Type"])

                # 6. Confidence - 目标置信度
                pt.confidence = int(rr["Confidence"])

                # 7. Lateral velocity (m/s) - 横向速度（米/秒）
                # 通过纵向速度和横向/纵向距离比值计算
                if pt.dRel != 0:
                    pt.yvRel = pt.vRel * math.sin(math.radians(pt.yRel / pt.dRel))
                else:
                    pt.yvRel = 0.0

                # Mark as valid measurement（标记为有效测量）
                pt.measured = True
            else:
                # Remove invalid target from tracking list（删除无效目标）
                if target_id in self.pts:
                    del self.pts[target_id]

        except KeyError as e:
            # 容错处理：字段不存在时清空目标列表，避免崩溃
            self.pts.clear()
            ret.errors.canError = True
            return ret
        except Exception as e:
            # 其他异常：清空目标列表，标记CAN错误
            self.pts.clear()
            ret.errors.canError = True
            return ret

        # Convert tracked points to list（将跟踪字典转为列表返回）
        ret.points = list(self.pts.values())

        return ret