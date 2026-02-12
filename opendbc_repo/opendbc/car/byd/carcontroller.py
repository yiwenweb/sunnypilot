"""
BYD CarController - Vehicle control implementation.

Based on old version behavior analysis:
- 790 (ACC_MPC_STATE) on Bus 0 @ 100Hz — steering control
- 813 (ACC_HUD_ADAS) on Bus 0 @ 50Hz — HUD display
- 814 (ACC_CMD) on Bus 0 @ 50Hz — ACC accel command
- 815 (ACC_AEB) on Bus 0 @ 50Hz — AEB control
- 944 (PCM_BUTTONS) on Bus 2 @ 20Hz — button forwarding

=== （五）重要安全提醒 ===
1. 仅辅助，不可脱手，随时接管
2. 弯道、雨雪、标线模糊、施工路段慎用/关闭
3. 不识别行人、非机动车、静止障碍物
4. 升级后功能以4S店开通版本为准

核心修正说明：
1. 校验和算法替换为原厂补码校验（移除无效的0xAF参数）
2. 适配0km/h激活逻辑：HUD显示速度支持0km/h，不再强制最低30km/h
3. 确保横向扭矩与bydcan.py的±5Nm限制匹配
4. 修复815/944报文校验和计算错误
"""

from enum import StrEnum

from opendbc.can import CANPacker
from opendbc.car import Bus, structs
from numpy import clip
from opendbc.car.interfaces import CarControllerBase
from opendbc.car.lateral import apply_driver_steer_torque_limits
# 导入修正后的bydcan函数（已修复校验和、扭矩限制等）
from opendbc.car.byd.bydcan import (
    create_steering_control, create_acc_cmd, create_acc_hud, byd_checksum
)
from opendbc.car.byd.values import CarControllerParams, CanBus


class CarController(CarControllerBase):
    def __init__(self, dbc_names: dict[StrEnum, str], CP, CP_SP):
        super().__init__(dbc_names, CP, CP_SP)
        self.packer = CANPacker(dbc_names[Bus.pt])
        self.params = CarControllerParams(CP)

        # 初始化状态变量
        self.apply_steer_last = 0    # 上一帧转向扭矩值（用于速率限制）
        self.lkas_counter = 0        # 790报文计数器（0-15）
        self.acc_counter = 0         # 813/814/815报文计数器（0-15）
        self.btn_counter = 0         # 944报文计数器（0-15）
        self.frame = 0               # 总帧数（用于频率控制）

    def update(self, CC, CC_SP, CS, now_nanos) -> tuple[structs.CarControl.Actuators, list]:
        """
        核心控制逻辑：整合横向/纵向控制，生成所有CAN控制报文
        参数：
            CC: 车辆控制指令（latActive/longActive/actuators等）
            CC_SP: 阳光pilot扩展控制参数
            CS: 车辆状态（含车速、刹车、方向盘扭矩等）
            now_nanos: 当前时间戳（纳秒）
        返回：
            实际执行的执行器参数 + CAN发送列表
        """
        actuators = CC.actuators
        can_sends = []

        lat_active = CC.latActive    # 横向控制激活（LKAS）
        long_active = CC.longActive  # 纵向控制激活（ACC）

        # === 1. 横向控制 (790 ACC_MPC_STATE) — 100Hz ===
        # 仅在latActive时发送，避免与原厂MPC报文冲突
        if lat_active:
            # 计算目标转向扭矩（映射到硬件范围）
            new_steer = int(round(actuators.torque * self.params.STEER_MAX))
            # 扭矩速率限制 + 驾驶员对抗限制（和现代/丰田/大众等一致的标准逻辑）
            # 最终输出会在bydcan.py中二次限制到±5Nm（原厂硬件限制）
            apply_steer = apply_driver_steer_torque_limits(
                new_steer, self.apply_steer_last,
                CS.out.steeringTorque, self.params,
            )
        else:
            apply_steer = 0  # 横向未激活时扭矩置0
        self.apply_steer_last = apply_steer  # 更新上一帧扭矩

        # 发送790转向控制报文（latActive或CC.enabled时发送）
        if lat_active or CC.enabled:
            lkas_active = lat_active
            lkas_req_prepare = False  # 匹配旧版本：ReqPrepare大部分时间为0

            # 调用修正后的create_steering_control（含±5Nm扭矩限制、制动优先级）
            can_sends.append(create_steering_control(
                self.packer, self.CP, CS,
                apply_steer if lkas_active else 0,
                lkas_req_prepare,
                lkas_active,
                CC.hudControl,
                self.lkas_counter,
            ))
            self.lkas_counter = (self.lkas_counter + 1) & 0xF  # 计数器0-15循环

        # === 2. 纵向控制 (813/814/815) — 50Hz（每2帧发送一次） ===
        # EPS需要完整的ACC报文组才会回复LKAS_Prepared=1，因此横向激活时也需发送
        if lat_active or CC.enabled:
            if self.frame % 2 == 0:  # 50Hz频率控制（100Hz总帧频）
                # 2.1 813 ACC_HUD_ADAS — HUD显示报文
                # 修正：适配0km/h激活，不再强制最低30km/h
                if CC.enabled and CC.hudControl.setSpeed > 0:
                    hud_set_speed = CC.hudControl.setSpeed * 3.6  # m/s → km/h
                else:
                    # 横向-only模式：用当前车速（支持0km/h），不再强制+10
                    hud_set_speed = CS.out.vEgoCluster * 3.6

                can_sends.append(create_acc_hud(
                    self.packer, self.CP, CS,
                    set_speed=hud_set_speed,       # 支持0km/h设定值
                    has_lead=False,
                    set_distance=4,
                    acc_state=1,                   # ACC_ON（适配0km/h激活）
                    enabled=True,
                    counter=self.acc_counter,
                ))

                # 2.2 814 ACC_CMD — ACC加速度指令报文
                can_sends.append(create_acc_cmd(
                    self.packer, self.CP, CS,
                    mrr_lead_dist=100.0,
                    accel=actuators.accel if long_active else 0.0,
                    resume_from_standstill=True,   # 支持0km/h恢复巡航
                    standstill_state=(CS.out.vEgo < 0.1),  # 识别静止状态
                    long_active=long_active,
                    counter=self.acc_counter,
                ))

                # 2.3 815 ACC_AEB — AEB控制报文（空闲值，安全优先）
                can_sends.append(self._create_acc_aeb(self.acc_counter))
                self.acc_counter = (self.acc_counter + 1) & 0xF  # 计数器循环

        # === 3. 944 PCM_BUTTONS 转发到Bus2 — 20Hz（每5帧发送一次） ===
        if CC.enabled:
            if self.frame % 5 == 0:
                can_sends.append(self._forward_pcm_buttons(CS, True))
                self.btn_counter = (self.btn_counter + 1) & 0xF  # 计数器循环

        # === 4. 更新执行器实际值 ===
        new_actuators = actuators.as_builder()
        # 转向扭矩归一化（映射回-1~1范围）
        new_actuators.torque = float(self.apply_steer_last / self.params.STEER_MAX) if self.params.STEER_MAX else 0.0
        new_actuators.torqueOutputCan = int(self.apply_steer_last)  # CAN实际发送的扭矩值
        # 纵向加速度仅在激活时更新
        if long_active:
            new_actuators.accel = float(actuators.accel)

        self.frame += 1
        return new_actuators, can_sends

    def _create_acc_aeb(self, counter: int):
        """
        生成ACC_AEB (815) 报文（空闲模板）
        核心修正：使用原厂补码校验和算法（移除0xAF参数）
        参数：
            counter: 报文计数器（0-15）
        返回：
            (报文ID, 字节数据, CAN总线)
        """
        # 旧版本空闲模板，仅修改计数器和校验和
        dat = bytearray([0x05, 0x80, 0x02, 0x0f, 0xff, 0xff, 0x00, 0x00])
        dat[6] = (0xF << 4) | (counter & 0xF)  # 计数器写入byte6的低4位
        dat[7] = byd_checksum(dat)             # 修正：调用新的无参数校验和函数
        return (815, bytes(dat), CanBus.PT)

    def _forward_pcm_buttons(self, CS, enabled):
        """
        转发PCM_BUTTONS (944) 到Bus2，匹配旧版本激活/空闲状态
        核心修正：使用原厂补码校验和算法（移除0xAF参数）
        参数：
            CS: 车辆状态
            enabled: 是否启用openpilot
        返回：
            (报文ID, 字节数据, CAN总线)
        """
        # 初始化空闲状态字节
        dat = bytearray([0x00, 0xd0, 0xff, 0xff, 0xff, 0xff, 0x00, 0x00])
        if enabled:
            # 激活状态：匹配旧版本byte0=0x03, byte1=0xd1
            dat[0] = 0x03
            dat[1] = 0xd1
        # 计数器写入byte6（高4位）
        dat[6] = (self.btn_counter << 4) | 0xF
        # 修正：调用新的无参数校验和函数
        dat[7] = byd_checksum(dat)
        return (944, bytes(dat), CanBus.CAM)