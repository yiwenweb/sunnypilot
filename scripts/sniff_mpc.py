#!/usr/bin/env python3
"""抓取 790/813/814/815 在各 bus 上的情况"""
from panda import Panda
import time

p = Panda()
p.set_safety_mode(1)  # allOutput
time.sleep(0.5)

# 先看 can_recv 返回格式
sample = p.can_recv()
if sample:
    print(f"can_recv item length: {len(sample[0])}, sample: {sample[0]}")

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

print("\n=== 5秒内收到的 790/813/814/815 ===")
if not seen:
    print("未收到任何 790/813/814/815 消息!")
for key in sorted(seen.keys()):
    addr, bus = key
    print(f"  addr={addr} bus={bus} count={count[key]} data={seen[key]}")

# 也看看 Bus 2 上有没有其他消息
bus2_addrs = set()
start2 = time.time()
while time.time() - start2 < 2:
    msgs = p.can_recv()
    for msg in msgs:
        if len(msg) == 3:
            addr, dat, bus = msg
        elif len(msg) == 4:
            addr, _, dat, bus = msg
        else:
            continue
        if bus == 2:
            bus2_addrs.add(addr)

print(f"\nBus 2 上的所有地址: {sorted(bus2_addrs)}")
