#!/usr/bin/env python3
"""诊断 MADS v3 — 精确定位 REJECTED 原因
先停 openpilot: pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
"""
import time
from panda import Panda

def byd_checksum(byte_key, dat):
    dat = dat[:7] + b'\x00'
    first_sum = sum(b >> 4 for b in dat)
    second_sum = sum(b & 0xF for b in dat)
    remainder = second_sum >> 4
    second_sum += byte_key >> 4
    first_sum += byte_key & 0xF
    p1 = ((-first_sum + 9) & 0xF)
    p2 = ((-second_sum + 9) & 0xF)
    return (((p1 + (-remainder + 5)) << 4) + p2) & 0xFF

def make_790(torque, active, counter):
    """构造 790 — 匹配原厂 idle 格式"""
    b0 = 0x42  # AutoFullBeam=2, LeftLane=0, Config=1(ALARM)
    b1 = 0x81  # SETME2=1, MPC_State=0, AutoFullBeam=1
    if torque < 0:
        torque_raw = torque + 2048
    else:
        torque_raw = torque & 0x7FF
    b2 = torque_raw & 0xFF
    b3 = ((torque_raw >> 8) & 0x07)
    # ReqPrepare=0 (bit 3), Active (bit 4)
    b3 |= ((1 if active else 0) << 4)
    b4 = 0x71  # SETME5=1, RightLane=0, LKAS_State=7
    b5 = 0x00
    b6 = 0x0C | ((counter & 0xF) << 4)  # AlarmType=0, SETME7=3
    dat = bytearray([b0, b1, b2, b3, b4, b5, b6, 0x00])
    dat[7] = byd_checksum(0xAF, dat)
    return bytes(dat)

p = Panda()

try:
    from cereal.car import structs
    byd_safety = int(structs.CarParams.SafetyModel.byd)
except:
    byd_safety = 35

# 初始化
print("=== MADS 诊断 v3 ===")
p.set_safety_mode(byd_safety, param=0)
time.sleep(0.1)
p.set_alternative_experience(1024)
time.sleep(0.1)

h = p.health()
print(f"safety={h['safety_mode']} altExp={h['alternative_experience']}")
print(f"controls_allowed={h['controls_allowed']}")

# 等待 CAN 消息稳定
p.can_clear(0xFFFF)
time.sleep(0.5)

# 检查是否收到 RX 消息
print("\n--- 检查 RX 消息 ---")
rx_counts = {}
for _ in range(20):
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if bus == 0:
            key = f"{addr}:bus{bus}"
            rx_counts[key] = rx_counts.get(key, 0) + 1
    time.sleep(0.05)

for k, v in sorted(rx_counts.items()):
    print(f"  {k}: {v} msgs")

# 检查 health
h = p.health()
print(f"\nhealth after RX: controls_allowed={h['controls_allowed']}")

# 打印所有 health 字段
print("\n--- 完整 health ---")
for k, v in sorted(h.items()):
    print(f"  {k}: {v}")

# 等待 ACC ON
print("\n--- 等待 ACC 状态 ---")
acc_state = None
for _ in range(40):
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if addr == 944 and bus == 0:
            acc_state = bool((dat[1] >> 0) & 1)
    time.sleep(0.05)
print(f"ACC 状态: {'ON' if acc_state else 'OFF' if acc_state is not None else '未检测到'}")

if acc_state is False:
    print("请按 ACC 开关打开...")
    while True:
        msgs = p.can_recv()
        for addr, dat, bus in msgs:
            if addr == 944 and bus == 0:
                if bool((dat[1] >> 0) & 1):
                    acc_state = True
                    print("ACC 已打开!")
        if acc_state:
            break
        time.sleep(0.05)
    time.sleep(0.3)

# 再次检查 health
h = p.health()
print(f"\nACC ON 后 health: controls_allowed={h['controls_allowed']}")
print(f"  tx_blocked={h['safety_tx_blocked']}")

# 测试发送
print("\n--- 发送测试 ---")
p.can_clear(0xFFFF)
counter = 0

tests = [
    (0, False, "torque=0 active=0"),
    (0, True,  "torque=0 active=1"),
    (1, True,  "torque=1 active=1"),
    (1, False, "torque=1 active=0"),
]

for torque, active, desc in tests:
    results = []
    for i in range(3):
        msg = make_790(torque, active, counter)
        p.can_send(790, msg, 0)
        counter = (counter + 1) & 0xF
        time.sleep(0.05)
        msgs = p.can_recv()
        for addr, dat, bus in msgs:
            if addr == 790:
                if bus == 0 or bus == 128:
                    results.append("OK")
                elif bus == 192:
                    results.append("REJ")
                else:
                    results.append(f"bus{bus}")
    print(f"  {desc}: {' '.join(results)}")

# 最终 health
h = p.health()
print(f"\n最终: controls_allowed={h['controls_allowed']} tx_blocked={h['safety_tx_blocked']}")

p.close()
print("done")
