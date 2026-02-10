#!/usr/bin/env python3
"""诊断 is_lat_active 状态 — 直接用 panda API
先停 openpilot: pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3

步骤:
1. 设置 safety mode + MADS
2. 等待 ACC 按下
3. 先发 10 帧 torque=0 active=1 (让 valid_steer_req_count 积累)
4. 然后发 torque=-8 active=1
5. 观察是否 ACCEPTED
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

def make_790(torque, req_prepare, active, counter):
    """构造 790 消息
    byte[0]: AutoFullBeamState(2) | LeftLane(0) | Config(1 or 3) | SETME2(1)
    byte[1]: ReqHands(0) | MPC_State(0) | AutoFullBeam(1)
    byte[2-3]: LKAS_Output(11bit) | ReqPrepare(1bit) | Active(1bit) | ...
    byte[4]: SETME5(1) | RightLane(0) | LKAS_State(7 or 2)
    byte[5]: ...
    byte[6]: counter | 0x0C
    byte[7]: checksum
    """
    # 原厂空闲: 42 81 00 40 71 00 xC CC
    # Config=1, LKAS_State=7, AutoFullBeam=1
    config = 3 if active else 1
    lkas_state = 2 if active else 7

    # byte[0]: AutoFullBeamState=2(bits 0-1), LeftLane=0(bits 2-3),
    #          Config(bits 6-7)
    b0 = 0x42 | ((config & 3) << 6)  # 0x42 for idle, 0xE2 for config=3
    b1 = 0x81  # SETME2=1, MPC_State=0, AutoFullBeam=1

    # LKAS_Output: 11-bit signed at bits 16-26
    # In little-endian: byte[2] has bits 16-23, byte[3] bits 24-31
    if torque < 0:
        torque_raw = torque + 2048  # convert signed to unsigned 11-bit
    else:
        torque_raw = torque
    b2 = torque_raw & 0xFF
    b3_low = (torque_raw >> 8) & 0x07  # bits 24-26

    # ReqPrepare at bit 27, Active at bit 28
    b3 = b3_low | ((1 if req_prepare else 0) << 3) | ((1 if active else 0) << 4)

    # byte[4]: SETME5=1(bit 32), RightLane=0(bits 33-34), LKAS_State(bits 36-39)
    b4 = 0x01 | ((lkas_state & 0xF) << 4)  # 0x71 for state=7, 0x21 for state=2

    b5 = 0x00
    b6 = ((counter & 0xF) << 4) | 0x0C

    dat = bytearray([b0, b1, b2, b3, b4, b5, b6, 0x00])
    dat[7] = byd_checksum(0xAF, dat)
    return bytes(dat)

p = Panda()
print(f"panda: {p.get_type()} fw={p.get_version()}")

# 设置 safety
try:
    from cereal.car import structs
    byd_safety = int(structs.CarParams.SafetyModel.byd)
except:
    byd_safety = 35

p.set_alternative_experience(1024)
p.set_safety_mode(byd_safety, param=0)
time.sleep(0.5)

h = p.health()
print(f"safety={h['safety_mode']} altExp={h['alternative_experience']} ctrl={h['controls_allowed']}")

print("\n=== 等待 ACC 按下 ===")
p.can_clear(0xFFFF)

acc_on = False
phase = "wait_acc"  # wait_acc -> warmup -> active
counter = 0
warmup_count = 0
active_count = 0

for i in range(600):
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if addr == 944 and bus == 0:
            new_acc = bool((dat[1] >> 0) & 1)
            if new_acc != acc_on:
                acc_on = new_acc
                print(f"[{i:3d}] ACC={'ON' if acc_on else 'OFF'}")
                if acc_on and phase == "wait_acc":
                    phase = "warmup"
                    warmup_count = 0
                    print(f"      -> Phase: warmup (发送 torque=0, active=1)")

        if addr == 790:
            if bus == 0:
                d = dat
                out = (d[2] | ((d[3] & 0x07) << 8))
                if out > 1023: out -= 2048
                act = (d[3] >> 4) & 1
                print(f"[{i:3d}] 790 ACCEPTED bus=0 Out={out} Act={act}")
            elif bus == 192:
                d = dat
                out = (d[2] | ((d[3] & 0x07) << 8))
                if out > 1023: out -= 2048
                act = (d[3] >> 4) & 1
                print(f"[{i:3d}] 790 REJECTED bus=192 Out={out} Act={act}")

    # 发送 790
    if phase == "warmup" and i % 2 == 0:
        # 先发 torque=0, active=1 让 valid_steer_req_count 积累
        msg = make_790(0, True, True, counter)
        p.can_send(790, msg, 0)
        counter = (counter + 1) & 0xF
        warmup_count += 1
        if warmup_count >= 20:
            phase = "active"
            active_count = 0
            print(f"\n[{i:3d}] -> Phase: active (发送 torque=-8, active=1)")

    elif phase == "active" and i % 2 == 0:
        torque = min(active_count, 8) * -1  # ramp: 0, -1, -2, ..., -8
        msg = make_790(torque, True, True, counter)
        p.can_send(790, msg, 0)
        counter = (counter + 1) & 0xF
        active_count += 1
        if active_count >= 30:
            phase = "done"
            print(f"\n[{i:3d}] -> Phase: done")

    # 定期打印 health
    if i % 50 == 0:
        h = p.health()
        print(f"[{i:3d}] health: ctrl={h['controls_allowed']} tx_blocked={h['safety_tx_blocked']}")

    if phase == "done" and active_count > 35:
        break

    time.sleep(0.05)

p.close()
print("\ndone")
