#!/usr/bin/env python3
"""追踪 is_lat_active 状态变化 — 通过发送测试消息判断
先停 openpilot: pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3

每 100ms 发送一个 torque=1 active=1 的 790:
- ACCEPTED → is_lat_active()=true
- REJECTED → is_lat_active()=false
同时打印时间戳，观察 is_lat_active 何时变 true/false
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

def make_790_test(torque, active, counter):
    """构造 790 测试消息"""
    config = 3 if active else 1
    lkas_state = 2 if active else 7
    b0 = 0x42 | ((config & 3) << 6)
    b1 = 0x81
    if torque < 0:
        torque_raw = torque + 2048
    else:
        torque_raw = torque & 0x7FF
    b2 = torque_raw & 0xFF
    b3 = ((torque_raw >> 8) & 0x07) | (1 << 3) | ((1 if active else 0) << 4)
    b4 = 0x01 | ((lkas_state & 0xF) << 4)
    b5 = 0x00
    b6 = ((counter & 0xF) << 4) | 0x0C
    dat = bytearray([b0, b1, b2, b3, b4, b5, b6, 0x00])
    dat[7] = byd_checksum(0xAF, dat)
    return bytes(dat)

p = Panda()
try:
    from cereal.car import structs
    byd_safety = int(structs.CarParams.SafetyModel.byd)
except:
    byd_safety = 35

p.set_alternative_experience(1024)
p.set_safety_mode(byd_safety, param=0)
time.sleep(0.5)

h = p.health()
print(f"safety={h['safety_mode']} altExp={h['alternative_experience']}")
print("\n=== 按 ACC 开关，然后观察 is_lat_active 状态 ===")
print("每行: 时间 | ACC状态 | 发送torque=1,active=1 | 结果")
print()

p.can_clear(0xFFFF)
counter = 0
acc_on = False
start_time = time.time()
lat_active_last = None

for i in range(400):
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if addr == 944 and bus == 0:
            new_acc = bool((dat[1] >> 0) & 1)
            if new_acc != acc_on:
                acc_on = new_acc
                t = time.time() - start_time
                print(f"  [{t:6.1f}s] ACC={'ON' if acc_on else 'OFF'}")

    # 每 100ms 发送一个测试 790 (torque=1, active=1)
    if i % 2 == 0:
        msg = make_790_test(1, True, counter)
        p.can_send(790, msg, 0)
        counter = (counter + 1) & 0xF

    # 检查回声
    time.sleep(0.02)
    echo = p.can_recv()
    for addr, dat, bus in echo:
        if addr == 790:
            out = (dat[2] | ((dat[3] & 0x07) << 8))
            if out > 1023: out -= 2048
            act = (dat[3] >> 4) & 1
            if out == 1 and act == 1:  # 我们发送的测试消息
                lat_active = (bus == 0)
                if lat_active != lat_active_last:
                    t = time.time() - start_time
                    status = "ACCEPTED (lat_active=TRUE)" if lat_active else "REJECTED (lat_active=FALSE)"
                    print(f"  [{t:6.1f}s] 790 test: {status}")
                    lat_active_last = lat_active

        # 也检查 944 回声
        if addr == 944 and bus == 0:
            new_acc = bool((dat[1] >> 0) & 1)
            if new_acc != acc_on:
                acc_on = new_acc
                t = time.time() - start_time
                print(f"  [{t:6.1f}s] ACC={'ON' if acc_on else 'OFF'}")

    time.sleep(0.03)

p.close()
print("\ndone")
