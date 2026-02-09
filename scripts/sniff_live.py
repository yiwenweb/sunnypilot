#!/usr/bin/env python3
"""在 openpilot 运行时通过 cereal 抓取 CAN 消息（不杀进程）"""
from cereal import messaging
import time

sm = messaging.SubMaster(['can', 'sendcan'])

target_addrs = {790, 813, 814, 815}
seen_can = {}
seen_sendcan = {}
count_can = {}
count_sendcan = {}

print("=== 抓取 CAN 消息 5 秒 ===")
start = time.time()
while time.time() - start < 5:
    sm.update(100)
    if sm.updated['can']:
        for msg in sm['can']:
            if msg.address in target_addrs:
                key = (msg.address, msg.src)
                count_can[key] = count_can.get(key, 0) + 1
                if key not in seen_can:
                    seen_can[key] = bytes(msg.dat).hex()
    if sm.updated['sendcan']:
        for msg in sm['sendcan']:
            if msg.address in target_addrs:
                key = (msg.address, msg.src)
                count_sendcan[key] = count_sendcan.get(key, 0) + 1
                if key not in seen_sendcan:
                    seen_sendcan[key] = bytes(msg.dat).hex()

print("\n--- CAN (接收到的) ---")
if not seen_can:
    print("  无 790/813/814/815")
for key in sorted(seen_can.keys()):
    addr, bus = key
    print(f"  addr={addr} bus={bus} count={count_can[key]} data={seen_can[key]}")

print("\n--- SENDCAN (openpilot 发送的) ---")
if not seen_sendcan:
    print("  无 790/813/814/815 (openpilot 未发送)")
for key in sorted(seen_sendcan.keys()):
    addr, bus = key
    print(f"  addr={addr} bus={bus} count={count_sendcan[key]} data={seen_sendcan[key]}")
