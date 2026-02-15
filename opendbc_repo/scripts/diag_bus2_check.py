#!/usr/bin/env python3
"""
最简诊断: 检查 Bus 2 帧能否被 cereal 收到
在 C3 上运行: python3 /data/openpilot/opendbc_repo/scripts/diag_bus2_check.py

如果 Bus 2 帧数始终为 0，说明 panda 没有把 Bus 2 上 MPC 发出的帧传给 host。
这意味着透传模式的前提不成立，需要改用硬编码默认值。
"""
import time
import cereal.messaging as messaging

def main():
    sm = messaging.SubMaster(['can'])

    print("检查 Bus 2 帧是否出现在 cereal can topic...")
    print("等待 5 秒收集数据...\n")

    bus_counts = {0: {}, 1: {}, 2: {}}  # bus -> {addr: count}
    start = time.time()

    while time.time() - start < 5.0:
        sm.update(100)
        if sm.updated['can']:
            for msg in sm['can']:
                bus = msg.src
                addr = msg.address
                if bus not in bus_counts:
                    bus_counts[bus] = {}
                bus_counts[bus][addr] = bus_counts[bus].get(addr, 0) + 1

    print("=" * 60)
    for bus in sorted(bus_counts.keys()):
        addrs = bus_counts[bus]
        total = sum(addrs.values())
        print(f"\nBus {bus}: 总帧数={total}")
        if total > 0:
            for addr in sorted(addrs.keys()):
                cnt = addrs[addr]
                freq = cnt / 5.0
                mark = ""
                if bus == 2 and addr in (790, 813, 814, 815):
                    mark = " ← MPC 帧!"
                if bus == 0 and addr == 792:
                    mark = " ← EPS 792"
                if bus == 0 and addr == 790:
                    mark = " ← OP 发的 790"
                print(f"  addr={addr:4d} (0x{addr:03X})  count={cnt:5d}  freq={freq:.1f}Hz{mark}")
        else:
            print("  (无帧)")

    print("\n" + "=" * 60)
    bus2_total = sum(bus_counts.get(2, {}).values())
    bus2_790 = bus_counts.get(2, {}).get(790, 0)
    bus2_813 = bus_counts.get(2, {}).get(813, 0)
    bus2_814 = bus_counts.get(2, {}).get(814, 0)

    if bus2_total == 0:
        print("\n⚠️  Bus 2 帧数为 0!")
        print("   panda 没有把 Bus 2 上 MPC 的帧传给 host。")
        print("   透传模式无法工作，需要改用硬编码默认值。")
    elif bus2_790 == 0:
        print("\n⚠️  Bus 2 有帧但没有 790!")
        print("   MPC 的 ACC_MPC_STATE 帧没出现在 Bus 2。")
    else:
        print(f"\n✅ Bus 2 正常: 790={bus2_790}, 813={bus2_813}, 814={bus2_814}")
        print("   透传模式前提成立。")

if __name__ == "__main__":
    main()
