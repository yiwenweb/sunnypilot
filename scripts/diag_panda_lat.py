#!/usr/bin/env python3
"""诊断 panda 横向控制状态 - 检查 MADS controls_allowed_lat
必须先停止 openpilot: pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3

测试步骤:
1. 运行此脚本
2. 按 ACC 开关
3. 观察:
   - 790 出现在 bus=0 -> is_lat_active()=true -> 修复成功
   - 790 出现在 bus=192 -> is_lat_active()=false -> 仍有问题
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

def make_790(counter):
    """790 idle: ReqPrepare=1, Active=0, Output=0"""
    dat = bytearray([0xD2, 0x01, 0x00, 0x08, 0x05, 0x01, 0x00, 0x00])
    dat[6] = ((counter & 0xF) << 4) | 0x0C
    dat[7] = byd_checksum(0xAF, dat)
    return bytes(dat)

p = Panda()
print(f"panda type: {p.get_type()}")
print(f"panda fw: {p.get_version()}")

h = p.health()
print(f"\nsafety_mode={h['safety_mode']} controls_allowed={h['controls_allowed']}")
print(f"alternative_experience={h['alternative_experience']}")
print(f"harness={h['car_harness_status']}")

# 查找 BYD safety model 编号
try:
    from cereal.car import structs
    byd_safety = int(structs.CarParams.SafetyModel.byd)
    print(f"\nSafetyModel.byd = {byd_safety}")
except Exception as e:
    print(f"\n无法获取 SafetyModel.byd: {e}")
    byd_safety = None

# 设置 alternative_experience (ENABLE_MADS=1024)
p.set_alternative_experience(1024)
print("set alternative_experience=1024")

# 设置 BYD safety mode
if byd_safety is not None:
    p.set_safety_mode(byd_safety, param=0)
    print(f"set safety_mode={byd_safety}")
else:
    print("WARNING: 无法设置 BYD safety mode")

time.sleep(0.5)
h = p.health()
print(f"\nAfter setup: safety_mode={h['safety_mode']} controls_allowed={h['controls_allowed']} alt_exp={h['alternative_experience']}")

print(f"\n=== 监听 CAN ===")
print(f"请按 ACC 开关...")
print(f"790 bus=0 = ACCEPTED, bus=192 = REJECTED\n")

p.can_clear(0xFFFF)
acc_on_last = -1
counter_790 = 0
sending = False

for i in range(400):
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        if addr == 944 and bus == 0:
            acc_on = (dat[1] >> 0) & 1
            if acc_on != acc_on_last:
                print(f"[{i:3d}] 944: ACC={acc_on} {'ON' if acc_on else 'OFF'}")
                acc_on_last = acc_on
                if acc_on and not sending:
                    sending = True
                    print(f"      -> 开始发送测试 790...")

        if addr == 790:
            if bus == 0:
                print(f"[{i:3d}] 790 bus=0 ACCEPTED raw={dat.hex()}")
            elif bus == 192:
                print(f"[{i:3d}] 790 bus=192 REJECTED raw={dat.hex()}")
            elif bus != 128:
                print(f"[{i:3d}] 790 bus={bus} raw={dat.hex()}")

        if addr == 792 and bus == 0 and i % 40 == 0:
            prep = dat[0] & 1
            tfail = (dat[0] >> 2) & 1
            mt = ((dat[1] | (dat[2] << 8)) & 0xFFF)
            if mt > 2047: mt -= 4096
            print(f"[{i:3d}] 792: Prep={prep} TFail={tfail} MainT={mt}")

    if sending and i % 2 == 0:
        msg = make_790(counter_790)
        p.can_send(790, msg, 0)
        counter_790 = (counter_790 + 1) & 0xF

    if i % 100 == 0 and i > 0:
        h = p.health()
        print(f"\n  health[{i}]: controls_allowed={h['controls_allowed']} safety_tx_blocked={h['safety_tx_blocked']}\n")

    time.sleep(0.05)

p.close()
print("\ndone")
