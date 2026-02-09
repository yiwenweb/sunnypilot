#!/usr/bin/env python3
"""在 safety=byd 模式下抓取 790/813/814/815"""
from panda import Panda
import time

p = Panda()

# 设置 safety=byd (mode 35 based on earlier output)
print(f"当前 safety: {p.health()['safety_mode']}")
p.set_safety_mode(35, 0)  # byd mode, param=0
time.sleep(0.5)
h = p.health()
print(f"设置后 safety: {h['safety_mode']}, controls_allowed: {h['controls_allowed']}")

seen = {}
count = {}
start = time.time()
while time.time() - start < 5:
    msgs = p.can_recv()
    for msg in msgs:
        if len(msg) == 3:
            addr, dat, bus = msg
        elif len(msg) == 4:
            addr, _, dat, bus = msg
        else:
            continue
        if addr in [790, 813, 814, 815]:
            key = (addr, bus)
            count[key] = count.get(key, 0) + 1
            if key not in seen:
                seen[key] = dat.hex()

print("\n=== safety=byd 模式下 5秒内收到的 790/813/814/815 ===")
if not seen:
    print("未收到任何 790/813/814/815 消息!")
for key in sorted(seen.keys()):
    addr, bus = key
    print(f"  addr={addr} bus={bus} count={count[key]} data={seen[key]}")

h2 = p.health()
print(f"\n最终状态: safety={h2['safety_mode']}, controls_allowed={h2['controls_allowed']}")

# 恢复 allOutput
p.set_safety_mode(1)
