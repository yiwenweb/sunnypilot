#!/usr/bin/env python3
"""追踪 MADS 状态变化的每一步
先停 openpilot: pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3

这个脚本:
1. 设置 safety mode + MADS
2. 监听 CAN 消息，追踪 944(ACC) 和 578(DRIVE_STATE) 的到达
3. 每 500ms 发送一个 torque=1 active=1 的 790 测试
4. 打印每个关键事件的时间戳
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

# 关键: 先 set_safety_mode, 后 set_alternative_experience
# 这样 set_safety_hooks 先重置状态, 然后 set_alternative_experience 设置 system_enabled
p.set_safety_mode(byd_safety, param=0)
time.sleep(0.1)
p.set_alternative_experience(1024)
time.sleep(0.1)

h = p.health()
print(f"safety={h['safety_mode']} altExp={h['alternative_experience']}")

print("\n=== 追踪 MADS 状态 ===")
print("先关闭 ACC (如果已开), 等 2 秒, 然后按 ACC 开关\n")

p.can_clear(0xFFFF)
counter = 0
start_time = time.time()

acc_on_count = 0
drive_state_count = 0
test_count = 0
acc_val = None

for i in range(600):
    msgs = p.can_recv()
    t = time.time() - start_time

    for addr, dat, bus in msgs:
        # 追踪 944 (PCM_BUTTONS)
        if addr == 944 and bus == 0:
            new_acc = bool((dat[1] >> 0) & 1)
            acc_on_count += 1
            if new_acc != acc_val:
                acc_val = new_acc
                print(f"  [{t:6.2f}s] 944 #{acc_on_count}: ACC={'ON' if new_acc else 'OFF'}")

        # 追踪 578 (DRIVE_STATE)
        if addr == 578 and bus == 0:
            drive_state_count += 1
            gear = dat[5] & 0x7
            brake = (dat[4] >> 5) & 1
            if drive_state_count <= 5 or drive_state_count % 50 == 0:
                print(f"  [{t:6.2f}s] 578 #{drive_state_count}: gear={gear} brake={brake}")

        # 追踪 790 回声
        if addr == 790:
            out = (dat[2] | ((dat[3] & 0x07) << 8))
            if out > 1023: out -= 2048
            act = (dat[3] >> 4) & 1
            if out == 1 and act == 1:  # 我们的测试消息
                status = "ACCEPTED" if bus == 0 else "REJECTED"
                print(f"  [{t:6.2f}s] 790 test: {status} (bus={bus})")

    # 每 500ms 发送一个测试 790
    if i % 10 == 5:
        msg = make_790_test(1, True, counter)
        p.can_send(790, msg, 0)
        counter = (counter + 1) & 0xF
        test_count += 1

    # 每 2 秒打印 health
    if i % 40 == 0:
        h = p.health()
        print(f"  [{t:6.2f}s] health: ctrl={h['controls_allowed']} altExp={h['alternative_experience']} tx_blocked={h['safety_tx_blocked']}")

    time.sleep(0.05)

p.close()
print(f"\nTotal: 944={acc_on_count} 578={drive_state_count} tests={test_count}")
print("done")
