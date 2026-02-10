#!/usr/bin/env python3
"""诊断 MADS controls_allowed_lat — v2
先停 openpilot: pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3

测试步骤:
1. 设置 safety mode + MADS
2. 等待 ACC ON (用户按 ACC 开关)
3. 发送 torque=0, active=0 的 790 → 应该 ACCEPTED (不需要 is_lat_active)
4. 发送 torque=0, active=1 的 790 → 需要 is_lat_active=true
5. 如果 step 4 ACCEPTED → is_lat_active=true → 成功!
"""
import time
import struct
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

def make_790(torque, active, req_prepare, counter):
    """构造 790 消息"""
    config = 1  # ALARM (原厂默认)
    lkas_state = 7  # 原厂默认
    # byte 0: AutoFullBeamState[3:0]=2, LeftLaneState[5:4]=0, LKAS_Config[7:6]=config
    b0 = 0x02 | ((config & 3) << 6)
    # byte 1: SETME2=1(bit0-1), ReqHandsOn=0(bit2), MPC_State=0(bit3-6), AutoFullBeam=1(bit7)
    b1 = 0x81
    # byte 2-3: LKAS_Output[10:0] at bits 16-26, ReqPrepare at bit 27, Active at bit 28
    if torque < 0:
        torque_raw = torque + 2048
    else:
        torque_raw = torque & 0x7FF
    b2 = torque_raw & 0xFF
    b3 = ((torque_raw >> 8) & 0x07)
    b3 |= ((1 if req_prepare else 0) << 3)
    b3 |= ((1 if active else 0) << 4)
    # byte 4: SETME5=1(bit0-1), RightLaneState=0(bit2-3), LKAS_State(bit4-7)
    b4 = 0x01 | ((lkas_state & 0xF) << 4)
    # byte 5: TrafficSignRecognition_Result
    b5 = 0x00
    # byte 6: LKAS_AlarmType(bit1-2)=0, SETME7=3(bit3-4), COUNTER(bit4-7)
    b6 = 0x0C | ((counter & 0xF) << 4)
    dat = bytearray([b0, b1, b2, b3, b4, b5, b6, 0x00])
    dat[7] = byd_checksum(0xAF, dat)
    return bytes(dat)

print("=== MADS 诊断 v2 ===")
p = Panda()

try:
    from cereal.car import structs
    byd_safety = int(structs.CarParams.SafetyModel.byd)
except:
    byd_safety = 35

# 初始化: 先 set_safety_mode, 后 set_alternative_experience
p.set_safety_mode(byd_safety, param=0)
time.sleep(0.1)
p.set_alternative_experience(1024)
time.sleep(0.1)

h = p.health()
print(f"safety={h['safety_mode']} altExp={h['alternative_experience']}")
print(f"controls_allowed={h['controls_allowed']}")

# 清空 CAN buffer
p.can_clear(0xFFFF)
time.sleep(0.2)

# Phase 1: 等待 ACC 状态
print("\n--- Phase 1: 检测当前 ACC 状态 ---")
acc_state = None
for _ in range(40):  # 2 秒
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if addr == 944 and bus == 0:
            acc_state = bool((dat[1] >> 0) & 1)
    time.sleep(0.05)

print(f"当前 ACC 状态: {'ON' if acc_state else 'OFF' if acc_state is not None else '未检测到'}")

if acc_state is None:
    print("ERROR: 未收到 944 消息!")
    p.close()
    exit(1)

# Phase 2: 如果 ACC 已经 ON，先等它 OFF
if acc_state:
    print("\n--- Phase 2: ACC 已经 ON，请按 ACC 关闭 ---")
    while True:
        msgs = p.can_recv()
        for addr, dat, bus in msgs:
            if addr == 944 and bus == 0:
                if not bool((dat[1] >> 0) & 1):
                    acc_state = False
                    print("ACC 已关闭")
        if not acc_state:
            break
        time.sleep(0.05)
    time.sleep(1.0)

# Phase 3: 等待 ACC ON
print("\n--- Phase 3: 请按 ACC 开关打开 ---")
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

# 等待一小段时间让 MADS 状态机处理
time.sleep(0.3)

# 消耗掉 buffer 中的旧消息
p.can_clear(0xFFFF)
time.sleep(0.1)

# Phase 4: 测试 is_lat_active
print("\n--- Phase 4: 测试 is_lat_active ---")

counter = 0

# Test A: torque=0, active=0 → 应该总是 ACCEPTED
print("\nTest A: torque=0, active=0 (应该 ACCEPTED)")
for i in range(3):
    msg = make_790(0, False, False, counter)
    p.can_send(790, msg, 0)
    counter = (counter + 1) & 0xF
    time.sleep(0.05)
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if addr == 790:
            status = "ACCEPTED" if bus == 0 or bus == 128 else f"REJECTED(bus={bus})"
            print(f"  790 → {status}")

time.sleep(0.2)
p.can_clear(0xFFFF)

# Test B: torque=0, active=1 → 需要 is_lat_active=true
# steer_torque_cmd_checks: torque=0 不触发 "!is_lat_active && torque!=0" 检查
# 但 steer_req=1 with torque=0 会触发 steer_req_mismatch 逻辑
# 实际上 has_steer_req_tolerance=true, 所以允许短暂的 mismatch
# 但 valid_steer_req_count < min_valid_request_frames(10) 会导致 violation
# 所以先发 10+ 帧 active=1, torque=0 来积累 valid_steer_req_count
# 不对... steer_req_mismatch = (steer_req == 0) && (desired_torque != 0)
# 如果 steer_req=1, torque=0 → steer_req_mismatch=false → valid_steer_req_count++
# 所以 torque=0, active=1 不会触发 mismatch

print("\nTest B: torque=0, active=1 (需要 is_lat_active=true)")
for i in range(5):
    msg = make_790(0, True, True, counter)
    p.can_send(790, msg, 0)
    counter = (counter + 1) & 0xF
    time.sleep(0.05)
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if addr == 790:
            out = (dat[2] | ((dat[3] & 0x07) << 8))
            if out > 1023: out -= 2048
            act = (dat[3] >> 4) & 1
            status = "ACCEPTED" if bus == 0 or bus == 128 else f"REJECTED(bus={bus})"
            print(f"  790 torque={out} active={act} → {status}")

time.sleep(0.2)
p.can_clear(0xFFFF)

# Test C: torque=1, active=1 → 需要 is_lat_active=true + rate limit OK
# 先发 15 帧 active=1, torque=0 积累 valid_steer_req_count
print("\nTest C: 先发 15 帧 active=1 torque=0, 然后 torque=1")
for i in range(15):
    msg = make_790(0, True, True, counter)
    p.can_send(790, msg, 0)
    counter = (counter + 1) & 0xF
    time.sleep(0.02)
    p.can_recv()  # 消耗回声

time.sleep(0.1)
p.can_clear(0xFFFF)

# 现在发 torque=1
print("  发送 torque=1, active=1:")
msg = make_790(1, True, True, counter)
p.can_send(790, msg, 0)
counter = (counter + 1) & 0xF
time.sleep(0.1)
msgs = p.can_recv()
for addr, dat, bus in msgs:
    if addr == 790:
        out = (dat[2] | ((dat[3] & 0x07) << 8))
        if out > 1023: out -= 2048
        act = (dat[3] >> 4) & 1
        status = "ACCEPTED" if bus == 0 or bus == 128 else f"REJECTED(bus={bus})"
        print(f"  790 torque={out} active={act} → {status}")

# 打印最终 health
h = p.health()
print(f"\n最终 health: controls_allowed={h['controls_allowed']} tx_blocked={h['safety_tx_blocked']}")

p.close()
print("\ndone")
