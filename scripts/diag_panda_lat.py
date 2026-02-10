#!/usr/bin/env python3
"""直接通过 panda API 检查 controls_allowed_lat 和 MADS 状态
必须先停止 openpilot: pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
"""
import time
from panda import Panda

p = Panda()
print(f"panda type: {p.get_type()}")
print(f"panda fw: {p.get_version()}")

# 读取 health 信息
h = p.health()
print(f"\n=== panda health ===")
print(f"  safety_model: {h.get('safety_mode', 'N/A')}")
print(f"  controls_allowed: {h.get('controls_allowed', 'N/A')}")
print(f"  alternative_experience: {h.get('alternative_experience', 'N/A')}")

# 设置 safety mode 为 BYD (和 openpilot 一样)
# SafetyModel.byd 的值需要查
# 先用 allOutput 模式测试
print(f"\n=== 设置 safety mode ===")
# 先设置 alternative_experience
p.set_alternative_experience(1024)  # ENABLE_MADS
print(f"  set alternative_experience=1024 (ENABLE_MADS)")

# 设置 MADS params
p.set_mads_params(True, False, False)  # enable_mads=True, disengage_on_brake=False, pause_on_brake=False
print(f"  set mads_params(True, False, False)")

# 现在读取 CAN 消息，模拟 ACC 开关按下
print(f"\n=== 监听 CAN 并检查 MADS 状态 ===")
print(f"请按 ACC 开关...")

p.can_clear(0xFFFF)
for i in range(200):
    msgs = p.can_recv()
    for addr, dat, bus in msgs:
        # PCM_BUTTONS (944) on Bus 0
        if addr == 944 and bus == 0:
            acc_on = (dat[1] >> 0) & 1  # bit 8
            print(f"  944: ACC_OnOff={acc_on} raw={dat.hex()}")

        # ACC_EPS_STATE (792) on Bus 0
        if addr == 792 and bus == 0:
            prepared = dat[0] & 1
            cruise_act = (dat[0] >> 1) & 1
            torque_fail = (dat[0] >> 2) & 1
            if i % 20 == 0:
                print(f"  792: Prep={prepared} CruAct={cruise_act} TFail={torque_fail} raw={dat.hex()}")

    # 检查 health
    if i % 50 == 0:
        h = p.health()
        print(f"\n  health[{i}]: controls_allowed={h.get('controls_allowed')} alt_exp={h.get('alternative_experience')}")

    time.sleep(0.05)

p.close()
print("done")
