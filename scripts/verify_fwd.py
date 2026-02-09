#!/usr/bin/env python3
"""
验证 panda 固件的 790/814 转发是否正常工作。

使用方法:
  pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
  python3 /data/openpilot/scripts/verify_fwd.py

预期结果:
  - safety=noOutput 时: 790/813/814/815 都应该在 bus=0 和 bus=128 上出现
  - safety=byd, controls_allowed=0 时: 790/813/814/815 应该从 bus=2 转发到 bus=0 (bus=128)
  - 如果 790/814 只在 bus=2 上出现但没有 bus=128，说明 static blocking 仍然生效
"""

import time
from panda import Panda

WATCH_ADDRS = {790, 813, 814, 815}

def sniff(p, duration=3):
    """收集指定时间内的 CAN 消息"""
    seen = {}  # (addr, bus) -> count
    end = time.time() + duration
    while time.time() < end:
        for msg in p.can_recv():
            addr, _, dat, bus = msg
            if addr in WATCH_ADDRS:
                key = (addr, bus)
                seen[key] = seen.get(key, 0) + 1
    return seen

def main():
    p = Panda()
    print(f"Panda: {p.get_version()}")
    print(f"MCU: {p.get_mcu_type()}")
    print()

    # --- Test 1: noOutput 模式 (默认转发) ---
    print("=" * 50)
    print("Test 1: safety=noOutput (默认转发)")
    print("=" * 50)
    p.set_safety_mode(Panda.SAFETY_NOOUTPUT)
    time.sleep(0.5)
    p.can_clear(0xFFFF)
    seen = sniff(p, 3)

    for addr in sorted(WATCH_ADDRS):
        buses = []
        for bus in [0, 2, 128]:
            cnt = seen.get((addr, bus), 0)
            if cnt > 0:
                buses.append(f"bus={bus}({cnt})")
        print(f"  addr={addr}: {', '.join(buses) if buses else '未收到'}")

    # --- Test 2: BYD 模式, controls_allowed=0 ---
    print()
    print("=" * 50)
    print("Test 2: safety=byd, controls_allowed=0")
    print("=" * 50)
    p.set_safety_mode(Panda.SAFETY_BYD)
    time.sleep(0.5)
    h = p.health()
    print(f"  safety_mode={h['safety_mode']}, controls_allowed={h['controls_allowed']}")
    p.can_clear(0xFFFF)
    seen = sniff(p, 3)

    all_ok = True
    for addr in sorted(WATCH_ADDRS):
        buses = []
        for bus in [0, 2, 128]:
            cnt = seen.get((addr, bus), 0)
            if cnt > 0:
                buses.append(f"bus={bus}({cnt})")
        status = "OK" if seen.get((addr, 128), 0) > 0 else "BLOCKED!"
        if status == "BLOCKED!":
            all_ok = False
        print(f"  addr={addr}: {', '.join(buses) if buses else '未收到'} [{status}]")

    # --- 结论 ---
    print()
    print("=" * 50)
    if all_ok:
        print("结果: 所有消息转发正常! check_relay=false 生效")
    else:
        print("结果: 部分消息被阻止! 固件可能未正确编译")
        print("  请重新运行 build_panda_on_c3.sh 并检查输出")
    print("=" * 50)

    # 恢复 noOutput
    p.set_safety_mode(Panda.SAFETY_NOOUTPUT)
    p.close()

if __name__ == "__main__":
    main()
