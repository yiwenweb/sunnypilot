#!/usr/bin/env python3
"""
BYD CAN 消息频率诊断工具

在 C3 上运行，监控所有 BYD carstate 消息的实际到达频率。
用于确定哪些消息是周期性的（可以设频率检查），哪些是事件触发的（需要 ignore_alive）。

使用方法:
  ssh comma@<C3_IP>
  cd /data/openpilot
  python3 opendbc_repo/scripts/diag_msg_freq.py

操作说明:
  1. 先静止不动方向盘，观察 30 秒
  2. 然后转动方向盘，再观察 30 秒
  3. 按 Ctrl+C 结束，查看汇总报告
  4. 把输出截图发给开发者
"""

import time
import cereal.messaging as messaging

# BYD carstate 监控的所有消息 (地址, 名称, Bus)
MESSAGES = [
    (0x11F, "EPS",           0),  # 287
    (0x121, "CARSPEED",      0),  # 289
    (0x242, "DRIVE_STATE",   0),  # 578
    (0x342, "PEDAL",         0),  # 834
    (0x318, "ACC_EPS_STATE", 0),  # 792
    (0x3B0, "PCM_BUTTONS",   0),  # 944
    (0x2A0, "YAW_RATE",      0),  # 672
    (0x2A2, "AXAY",          0),  # 674
    (0x2C1, "BCM",           0),  # 705
    (0x2C5, "STALKS",        0),  # 709
    (0x218, "EPB",           0),  # 536
]

def main():
    sm = messaging.SubMaster(['can'])

    # 每个消息的统计
    stats = {}
    for addr, name, bus in MESSAGES:
        stats[(addr, bus)] = {
            'name': name,
            'count': 0,
            'timestamps': [],
            'gaps': [],
            'max_gap': 0,
            'last_ts': None,
        }

    print("=" * 70)
    print("BYD CAN 消息频率诊断")
    print("先静止方向盘 30 秒，再转动方向盘 30 秒")
    print("按 Ctrl+C 结束查看报告")
    print("=" * 70)

    start_time = time.monotonic()
    last_print = start_time

    try:
        while True:
            sm.update(100)  # 100ms timeout

            if sm.updated['can']:
                now = time.monotonic()
                for msg in sm['can']:
                    key = (msg.address, msg.src)
                    if key in stats:
                        s = stats[key]
                        s['count'] += 1
                        if s['last_ts'] is not None:
                            gap = now - s['last_ts']
                            s['gaps'].append(gap)
                            if gap > s['max_gap']:
                                s['max_gap'] = gap
                        s['last_ts'] = now

                # 每 5 秒打印一次实时状态
                if now - last_print >= 5.0:
                    elapsed = now - start_time
                    print(f"\n--- {elapsed:.0f}s ---")
                    print(f"{'消息':<18} {'总数':>6} {'频率Hz':>8} {'最大间隔ms':>12} {'最近间隔ms':>12}")
                    for addr, name, bus in MESSAGES:
                        s = stats[(addr, bus)]
                        freq = s['count'] / elapsed if elapsed > 0 else 0
                        max_gap_ms = s['max_gap'] * 1000
                        last_gap_ms = s['gaps'][-1] * 1000 if s['gaps'] else 0
                        marker = " <<<" if max_gap_ms > 2000 else ""
                        print(f"{name:<18} {s['count']:>6} {freq:>8.1f} {max_gap_ms:>12.1f} {last_gap_ms:>12.1f}{marker}")
                    last_print = now

    except KeyboardInterrupt:
        pass

    # 汇总报告
    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 70)
    print(f"汇总报告 (运行 {elapsed:.1f} 秒)")
    print("=" * 70)
    print(f"{'消息':<18} {'总数':>6} {'平均Hz':>8} {'最大间隔ms':>12} {'建议':<20}")
    print("-" * 70)

    for addr, name, bus in MESSAGES:
        s = stats[(addr, bus)]
        freq = s['count'] / elapsed if elapsed > 0 else 0
        max_gap_ms = s['max_gap'] * 1000

        if s['count'] == 0:
            suggestion = "未收到! 检查DBC"
        elif max_gap_ms > 5000:
            suggestion = f"事件触发 → nan"
        elif max_gap_ms > 2000:
            suggestion = f"不稳定 → nan"
        elif freq > 5:
            safe_freq = max(1, int(freq * 0.4))
            suggestion = f"周期性 → {safe_freq}U"
        else:
            suggestion = f"低频 → 1U"

        print(f"{name:<18} {s['count']:>6} {freq:>8.1f} {max_gap_ms:>12.1f} {suggestion:<20}")

    print("-" * 70)
    print("建议说明:")
    print("  nan    = float('nan')，跳过存活检查（事件触发消息）")
    print("  数字U  = safety RxCheck 频率（Hz），超时 = 10/freq 秒")
    print("  <<< 标记 = 最大间隔超过 2 秒，可能是事件触发")
    print()
    print("请把以上输出截图发给开发者!")


if __name__ == "__main__":
    main()
