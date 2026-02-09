#!/usr/bin/env python3
"""
验证 panda 固件的 790/814 转发是否正常工作。

使用方法:
  pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
  python3 /data/openpilot/scripts/verify_fwd.py
"""

import time
from panda import Panda

# 直接用数字常量，避免 Panda 类属性不存在的问题
SAFETY_NOOUTPUT = 19
SAFETY_BYD = 35

WATCH_ADDRS = {790, 813, 814, 815}


def sniff(p, duration=3):
    seen = {}
    end = time.time() + duration
    while time.time() < end:
        for msg in p.can_recv():
            addr, _, dat, bus = msg
            if addr in WATCH_ADDRS:
                key = (addr, bus)
                seen[key] = seen.get(key, 0) + 1
    return seen


def print_result(seen):
    for addr in sorted(WATCH_ADDRS):
        buses = []
        for bus in [0, 2, 128]:
            cnt = seen.get((addr, bus), 0)
            if cnt > 0:
                buses.append(f"bus={bus}({cnt})")
        fwd_ok = seen.get((addr, 128), 0) > 0
        status = "OK" if fwd_ok else "BLOCKED!"
        print(f"  addr={addr}: {', '.join(buses) if buses else '未收到'} [{status}]")
    return all(seen.get((a, 128), 0) > 0 for a in WATCH_ADDRS)


def main():
    p = Panda()
    print(f"Panda: {p.get_version()}")
    print(f"MCU: {p.get_mcu_type()}")
    print()

    # Test 1: noOutput 模式
    print("=" * 50)
    print("Test 1: safety=noOutput (默认转发)")
    print("=" * 50)
    p.set_safety_mode(SAFETY_NOOUTPUT)
    time.sleep(0.5)
    p.can_clear(0xFFFF)
    seen = sniff(p, 3)
    print_result(seen)

    # Test 2: BYD 模式
    print()
    print("=" * 50)
    print("Test 2: safety=byd, controls_allowed=0")
    print("=" * 50)
    p.set_safety_mode(SAFETY_BYD)
    time.sleep(0.5)
    h = p.health()
    print(f"  safety={h['safety_mode']}, controls_allowed={h['controls_allowed']}")
    p.can_clear(0xFFFF)
    seen = sniff(p, 3)
    all_ok = print_result(seen)

    print()
    print("=" * 50)
    if all_ok:
        print("结果: 所有消息转发正常! check_relay=false 生效")
    else:
        print("结果: 部分消息被阻止! 固件未正确编译")
    print("=" * 50)

    p.set_safety_mode(SAFETY_NOOUTPUT)
    p.close()


if __name__ == "__main__":
    main()
