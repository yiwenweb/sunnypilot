#!/usr/bin/env python3
"""
BYD 全总线 CAN 嗅探工具

扫描 Bus 0/1/2 上的所有消息，重点查找：
  - BCM (301)、STALKS (307)：转向灯、车门、安全带
  - YAW_RATE (546)、AXAY (547)：横摆率、加速度
  - BSD_RADAR (1048)：盲区监测
  - BELT (660)：安全带（备选）
  以及所有未知消息

使用方法:
  ssh comma@<C3_IP>
  cd /data/openpilot
  python3 opendbc_repo/scripts/sniff_all_buses.py

操作说明:
  1. 车辆通电（ACC ON 或 启动）
  2. 运行脚本，等待 30-60 秒
  3. 期间可以：开关转向灯、开关车门、系/解安全带
  4. 按 Ctrl+C 结束，查看报告
  5. 把输出截图发给开发者
"""

import time
import cereal.messaging as messaging

# 重点关注的消息地址
TARGETS = {
    85:   "EPB",
    287:  "EPS",
    289:  "CARSPEED",
    301:  "BCM",
    307:  "STALKS",
    546:  "YAW_RATE",
    547:  "AXAY",
    578:  "DRIVE_STATE",
    660:  "BELT",
    694:  "DATETIME",
    790:  "ACC_MPC_STATE",
    792:  "ACC_EPS_STATE",
    813:  "ACC_HUD_ADAS",
    814:  "ACC_CMD",
    815:  "ACC_AEB",
    834:  "PEDAL",
    884:  "RADAR_MRR",
    944:  "PCM_BUTTONS",
    1048: "BSD_RADAR",
}

def main():
    sm = messaging.SubMaster(['can'])

    # stats[bus][addr] = {count, first_data, last_data, last_ts, max_gap, gaps}
    stats: dict[int, dict[int, dict]] = {0: {}, 1: {}, 2: {}}

    print("=" * 78)
    print("BYD 全总线 CAN 嗅探工具")
    print("扫描 Bus 0/1/2，查找 BCM/STALKS/YAW_RATE/AXAY/BSD_RADAR 等消息")
    print("请开关转向灯、车门、安全带以触发相关消息")
    print("按 Ctrl+C 结束查看报告")
    print("=" * 78)

    start_time = time.monotonic()
    last_print = start_time

    try:
        while True:
            sm.update(100)

            if sm.updated['can']:
                now = time.monotonic()
                for msg in sm['can']:
                    bus = msg.src
                    addr = msg.address
                    if bus not in stats:
                        stats[bus] = {}

                    if addr not in stats[bus]:
                        stats[bus][addr] = {
                            'count': 0,
                            'first_data': bytes(msg.dat),
                            'last_data': bytes(msg.dat),
                            'last_ts': None,
                            'max_gap': 0,
                            'min_gap': 999,
                        }

                    s = stats[bus][addr]
                    s['count'] += 1
                    s['last_data'] = bytes(msg.dat)
                    if s['last_ts'] is not None:
                        gap = now - s['last_ts']
                        if gap > s['max_gap']:
                            s['max_gap'] = gap
                        if gap < s['min_gap']:
                            s['min_gap'] = gap
                    s['last_ts'] = now

                # 每 10 秒打印实时状态（只显示重点消息）
                if now - last_print >= 10.0:
                    elapsed = now - start_time
                    print(f"\n--- {elapsed:.0f}s 实时状态 ---")
                    for bus in sorted(stats.keys()):
                        found = []
                        for addr in sorted(stats[bus].keys()):
                            if addr in TARGETS:
                                s = stats[bus][addr]
                                freq = s['count'] / elapsed
                                found.append(f"  {TARGETS[addr]}({addr}) = {s['count']}条, {freq:.1f}Hz")
                        if found:
                            print(f"Bus {bus}: {len(stats[bus])} 个地址")
                            for line in found:
                                print(line)
                        else:
                            print(f"Bus {bus}: {len(stats[bus])} 个地址 (无重点消息)")
                    last_print = now

    except KeyboardInterrupt:
        pass

    elapsed = time.monotonic() - start_time
    if elapsed < 1:
        print("运行时间太短，请至少运行 10 秒")
        return

    # ==================== 汇总报告 ====================
    print("\n" + "=" * 78)
    print(f"全总线嗅探报告 (运行 {elapsed:.1f} 秒)")
    print("=" * 78)

    # 1. 重点消息查找结果
    print("\n【重点消息查找结果】")
    print(f"{'消息':<18} {'地址':>5} {'Bus':>4} {'总数':>7} {'频率Hz':>8} {'数据(首帧)':>20}")
    print("-" * 78)

    critical = ["BCM", "STALKS", "YAW_RATE", "AXAY", "BSD_RADAR", "BELT"]
    for name in critical:
        addr = [a for a, n in TARGETS.items() if n == name][0]
        found_on = []
        for bus in sorted(stats.keys()):
            if addr in stats[bus]:
                s = stats[bus][addr]
                freq = s['count'] / elapsed
                data_hex = s['first_data'][:8].hex(' ')
                found_on.append((bus, s['count'], freq, data_hex))

        if found_on:
            for bus, count, freq, data_hex in found_on:
                print(f"{name:<18} {addr:>5} {bus:>4} {count:>7} {freq:>8.1f} {data_hex:>20}")
        else:
            print(f"{name:<18} {addr:>5}    -       0      0.0  *** 未找到 ***")

    # 2. 各总线完整消息列表
    for bus in sorted(stats.keys()):
        addrs = sorted(stats[bus].keys())
        if not addrs:
            continue

        print(f"\n【Bus {bus} 完整消息列表】({len(addrs)} 个地址)")
        print(f"{'地址':>6} {'名称':<18} {'总数':>7} {'频率Hz':>8} {'最大间隔ms':>12} {'数据(首帧)'}")
        print("-" * 78)

        for addr in addrs:
            s = stats[bus][addr]
            name = TARGETS.get(addr, f"UNK_{addr}")
            freq = s['count'] / elapsed
            max_gap_ms = s['max_gap'] * 1000
            data_hex = s['first_data'][:8].hex(' ')
            marker = " ★" if name in critical else ""
            print(f"{addr:>6} {name:<18} {s['count']:>7} {freq:>8.1f} {max_gap_ms:>12.1f}  {data_hex}{marker}")

    # 3. 建议
    print("\n" + "=" * 78)
    print("【适配建议】")
    print("-" * 78)

    for name in critical:
        addr = [a for a, n in TARGETS.items() if n == name][0]
        buses_found = [bus for bus in stats if addr in stats[bus] and stats[bus][addr]['count'] > 0]

        if not buses_found:
            print(f"  {name} ({addr}): 所有总线均未收到。可能地址不对，或需要特定操作触发。")
        elif 0 in buses_found:
            freq = stats[0][addr]['count'] / elapsed
            print(f"  {name} ({addr}): ✅ 在 Bus 0 上，{freq:.1f}Hz。可直接加入 carstate.py 解析。")
        else:
            for bus in buses_found:
                freq = stats[bus][addr]['count'] / elapsed
                print(f"  {name} ({addr}): 在 Bus {bus} 上，{freq:.1f}Hz。需要加 Bus {bus} 的 CANParser。")

    print()
    print("请把以上输出截图发给开发者!")
    print("如果 BCM/STALKS 在 Bus 1 或 Bus 2 上，我们可以加多总线解析。")


if __name__ == "__main__":
    main()
