#!/usr/bin/env python3
"""
BYD 帧对比诊断工具

同时抓取 Bus 0 和 Bus 2 上的 790/813/814/815，
逐字节对比 openpilot 帧和原厂 MPC 帧的差异。

关键：在 openpilot 运行时，Bus 2 上是原厂 MPC 的帧，
Bus 0 上可能是 openpilot 的帧（如果控制激活）或 MPC 转发的帧。

使用方法:
  ssh comma@<C3_IP>
  python3 /data/openpilot/opendbc_repo/scripts/diag_frame_compare.py

  然后按 ACC 开启，观察 Bus 0 和 Bus 2 的帧差异
"""

import time
import cereal.messaging as messaging

WATCH_ADDRS = {790, 792, 813, 814, 815}
NAMES = {790: "790_MPC", 792: "792_EPS", 813: "813_HUD", 814: "814_CMD", 815: "815_AEB"}

def hex_str(data):
    return " ".join(f"{b:02x}" for b in data)

def chk_ok(data):
    return sum(data[:8]) & 0xFF == 0xFF

def main():
    sm = messaging.SubMaster(['can', 'selfdriveState', 'carControl', 'carState'])

    # 最新帧: {(bus, addr): bytes}
    latest = {}
    start = time.monotonic()
    last_report = 0

    print("=" * 70)
    print("BYD 帧对比诊断 — 逐字节对比 Bus 0 vs Bus 2")
    print("=" * 70)
    print("按 ACC 开启后观察输出")
    print("重点看: Bus 0 和 Bus 2 同一地址的帧是否一致")
    print("如果 Bus 0 有帧但 Bus 2 没有 → fwd_hook 在拦截")
    print("如果 Bus 0 和 Bus 2 帧不同 → openpilot 在发送替代帧")
    print()

    try:
        while True:
            sm.update(100)
            if not sm.updated['can']:
                continue

            now = time.monotonic() - start
            for msg in sm['can']:
                bus = msg.src
                addr = msg.address
                if addr not in WATCH_ADDRS or bus not in (0, 2):
                    continue
                latest[(bus, addr)] = bytes(msg.dat)

            # 每 1 秒报告
            if now - last_report < 1.0:
                continue
            last_report = now

            # openpilot 状态
            if sm.valid['selfdriveState']:
                ss = sm['selfdriveState']
                print(f"\n[{now:.0f}s] OP: enabled={ss.enabled} active={ss.active}")
            if sm.valid['carControl']:
                cc = sm['carControl']
                print(f"  CC: latActive={cc.latActive} longActive={cc.longActive}")
            if sm.valid['carState']:
                cs = sm['carState']
                print(f"  CS: cruiseAvail={cs.cruiseState.available} vEgo={cs.vEgo:.1f}")

            # 帧对比
            for addr in sorted(WATCH_ADDRS):
                b0 = latest.get((0, addr))
                b2 = latest.get((2, addr))
                name = NAMES[addr]

                if b0 and b2:
                    # 对比（忽略 counter 和 checksum: byte[6] 和 byte[7]）
                    same = b0[:6] == b2[:6]
                    c0 = "✓" if chk_ok(b0) else "✗"
                    c2 = "✓" if chk_ok(b2) else "✗"
                    if same:
                        print(f"  {name}: Bus0=Bus2 (MPC转发) CHK0={c0} CHK2={c2}")
                    else:
                        print(f"  {name}: *** 不同 ***")
                        print(f"    Bus0: {hex_str(b0)} CHK{c0}")
                        print(f"    Bus2: {hex_str(b2)} CHK{c2}")
                        # 逐字节差异
                        for i in range(min(len(b0), len(b2))):
                            if b0[i] != b2[i]:
                                print(f"    byte[{i}]: Bus0=0x{b0[i]:02X} Bus2=0x{b2[i]:02X}")
                elif b0 and not b2:
                    c0 = "✓" if chk_ok(b0) else "✗"
                    print(f"  {name}: 仅Bus0 {hex_str(b0)} CHK{c0} (Bus2被拦截或MPC未发)")
                elif b2 and not b0:
                    c2 = "✓" if chk_ok(b2) else "✗"
                    print(f"  {name}: 仅Bus2 {hex_str(b2)} CHK{c2} (Bus0未收到)")
                else:
                    print(f"  {name}: 无数据")

    except KeyboardInterrupt:
        print("\n诊断结束")

if __name__ == "__main__":
    main()
