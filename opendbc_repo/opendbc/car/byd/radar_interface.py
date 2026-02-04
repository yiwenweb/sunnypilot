# BYD雷达接口 - sunnypilot 0.10.1
# 专为比亚迪18款唐DM及其他BYD车型优化
# 版本: 2026.02 稳定版

from opendbc.can import CANParser
from opendbc.car import Bus, structs
from opendbc.car.interfaces import RadarInterfaceBase
from opendbc.car.byd.values import DBC, CanBus


class RadarInterface(RadarInterfaceBase):
    """BYD雷达接口类"""

    def __init__(self, CP, CP_SP):
        super().__init__(CP, CP_SP)

        # 雷达点字典
        self.pts: dict[int, structs.RadarData.RadarPoint] = {}

        # 初始化CAN解析器
        if Bus.radar in DBC[CP.carFingerprint]:
            self.rcp = CANParser(
                DBC[CP.carFingerprint][Bus.radar],
                [("RADAR_MRR", 20)],
                CanBus.RADAR,
            )
        else:
            self.rcp = None

        # 跟踪状态
        self.trigger_msg = 0x374  # 触发报文ID
        self.track_id = 0

    def update(self, can_packets) -> structs.RadarDataT | None:
        """更新雷达数据"""
        if self.rcp is None:
            return None

        # 更新CAN解析器
        self.rcp.update(can_packets)

        ret = structs.RadarData()
        errors = []

        # 检查CAN有效性
        if not self.rcp.can_valid:
            errors.append("canError")
            ret.errors = errors
            return ret

        # 解析雷达报文
        rr = self.rcp.vl["RADAR_MRR"]

        # 检查目标有效性
        if rr["IsValid"] == 1:
            # 创建或更新雷达点
            if self.track_id not in self.pts:
                self.pts[self.track_id] = structs.RadarData.RadarPoint()

            pt = self.pts[self.track_id]

            # 纵向距离 (米)
            pt.dRel = rr["LongDist"]

            # 横向距离 (米)
            pt.yRel = rr["LatDist"]

            # 相对速度 (需要从其他报文获取，这里暂时设为0)
            pt.vRel = 0.0

            # 目标类型
            pt.measured = True

            self.track_id = (self.track_id + 1) % 256
        else:
            # 清除无效目标
            self.pts.clear()

        ret.points = list(self.pts.values())
        ret.errors = errors

        return ret
