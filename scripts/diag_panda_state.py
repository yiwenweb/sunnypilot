#!/usr/bin/env python3
"""直接查询 panda 内部状态 — 检查 is_lat_active / controls_allowed / mads 状态
在 C3 上运行前先停 openpilot:
  pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
然后:
  python3 /data/openpilot/scripts/diag_panda_state.py
"""
import time
import struct

try:
    from panda import Panda
except ImportError:
    import sys
    sys.path.insert(0, '/data/openpilot/panda/python')
    from panda import Panda

p = Panda()
print(f"Panda FW: {p.get_version()}")
print(f"Safety model: {p.get_safety_mode()}")

# 设置 BYD safety mode (safety_param=0, 非 stock longitudinal)
# SafetyModel.byd = 在 safety_declarations.h 中定义
# 先查看当前 safety mode
cur_mode = p.get_safety_mode()
print(f"Current safety mode: {cur_mode}")

# 读取 panda 的 health 信息
health = p.health()
print(f"\nPanda health:")
print(f"  controls_allowed: {health.get('controls_allowed', 'N/A')}")
print(f"  controls_allowed_lat: {health.get('controls_allowed_lat', 'N/A')}")
print(f"  safety_mode: {health.get('safety_mode', 'N/A')}")
print(f"  safety_param: {health.get('safety_param', 'N/A')}")

# 监听 CAN 消息并尝试发送 790
print("\n=== 监听 CAN 并测试 TX 790 ===")
print("请按 ACC 开关激活 MADS，然后观察...")

# 先清空 CAN buffer
p.can_clear(0xFFFF)
time.sleep(0.1)

for i in range(200):
    # 读取 CAN 消息
    msgs = p.can_recv()
    
    saw_944 = False
    saw_578 = False
    for addr, dat, bus in msgs:
        # 检查 PCM_BUTTONS (944) 上的 ACC 开关状态
        if addr == 944 and bus == 0:
            acc_on = (dat[1] >> 0) & 1  # bit 8 = byte[1] bit 0
            saw_944 = True
            if i % 20 == 0:
                print(f"[{i:3d}] 944: ACC_on={acc_on} raw={dat.hex()}")
        
        # 检查 DRIVE_STATE (578)
        if addr == 578 and bus == 0:
            gear = dat[5] & 0x7
            brake = (dat[4] >> 5) & 1  # bit 37
            saw_578 = True
    
    # 每 20 帧查询一次 health
    if i % 20 == 0:
        h = p.health()
        ca = h.get('controls_allowed', '?')
        cal = h.get('controls_allowed_lat', '?')
        print(f"[{i:3d}] health: controls_allowed={ca} controls_allowed_lat={cal}")
    
    # 每 50 帧尝试发送一个 790 (torque=0, req=0, active=0) 看是否被接受
    if i % 50 == 0 and i > 0:
        # 原厂 MPC 空闲格式: 42 81 00 40 71 00 xC CC
        test_dat = bytes([0x42, 0x81, 0x00, 0x40, 0x71, 0x00, 0x0C, 0x00])
        # 先不加 checksum，看 panda 是否接受
        p.can_send(0x316, test_dat, 0)  # 790 on bus 0
        time.sleep(0.02)
        
        # 检查是否被接受
        echo = p.can_recv()
        accepted = False
        rejected = False
        for addr, dat, bus in echo:
            if addr == 790:
                if bus == 0:
                    accepted = True
                elif bus == 192:
                    rejected = True
        print(f"[{i:3d}] TX 790 test: accepted={accepted} rejected={rejected}")
    
    time.sleep(0.05)

print("\ndone")
