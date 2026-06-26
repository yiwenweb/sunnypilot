#!/usr/bin/env python3
"""
离线分析 rlog 中的横向控制链路 (零运行时干扰)
=====================================================
读取已录制的 rlog, 统计横向相关状态, 判断横向卡在哪一环:

  1. carControl.latActive  -> OP 是否认为横向已激活
  2. carControl.actuators.torque / torqueOutputCan -> OP 想发多大扭矩
  3. sendcan 中 790(0x316) -> OP 实际发出的转向报文 (LKAS_Output/Active/ReqPrepare)
  4. can 中真实 EPS 792(0x318) 的 LKAS_Prepared -> EPS 是否进入准备状态

用法:
  # 找最近的 segment:
  #   ls -lt /data/media/0/realdata/ | head
  # 然后传入 segment 路径 (含 rlog):
  python3 /data/openpilot/scripts/analyze_rlog_lat.py /data/media/0/realdata/<route>--<seg>

  也可直接传 rlog 文件路径。
"""
import sys
import os


def find_rlog(path):
    if os.path.isfile(path):
        return path
    for name in ("rlog", "rlog.bz2", "rlog.zst"):
        cand = os.path.join(path, name)
        if os.path.isfile(cand):
            return cand
    raise FileNotFoundError(f"在 {path} 找不到 rlog")


def main(path):
    from openpilot.tools.lib.logreader import LogReader

    rlog = find_rlog(path)
    print(f"分析: {rlog}\n")

    lr = LogReader(rlog)

    n_cc = 0
    n_lat_active = 0
    n_long_active = 0
    torque_nonzero = 0
    max_torque = 0.0
    max_torque_can = 0

    n_790 = 0
    n_790_active = 0
    n_790_reqprep = 0
    sample_790 = []

    n_792 = 0
    n_792_prepared = 0
    sample_792 = []

    for msg in lr:
        w = msg.which()

        if w == 'carControl':
            cc = msg.carControl
            n_cc += 1
            if cc.latActive:
                n_lat_active += 1
            if cc.longActive:
                n_long_active += 1
            t = abs(cc.actuators.torque)
            tc = abs(cc.actuators.torqueOutputCan)
            if t > 0.001:
                torque_nonzero += 1
            max_torque = max(max_torque, t)
            max_torque_can = max(max_torque_can, int(tc))

        elif w == 'sendcan':
            for m in msg.sendcan:
                if m.address == 0x316:  # 790
                    d = bytes(m.dat)
                    if len(d) < 8:
                        continue
                    n_790 += 1
                    active = (d[3] >> 4) & 1
                    reqprep = (d[3] >> 3) & 1
                    out = (d[2] | ((d[3] & 0x07) << 8))
                    if out > 1023:
                        out -= 2048
                    if active:
                        n_790_active += 1
                    if reqprep:
                        n_790_reqprep += 1
                    if len(sample_790) < 5 and (active or reqprep):
                        sample_790.append((out, active, reqprep, d.hex()))

        elif w == 'can':
            for m in msg.can:
                if m.address == 0x318 and m.src == 0:  # 真实 EPS 792 on bus 0
                    d = bytes(m.dat)
                    if len(d) < 8:
                        continue
                    n_792 += 1
                    prepared = d[0] & 1   # LKAS_Prepared bit0
                    if prepared:
                        n_792_prepared += 1
                    if len(sample_792) < 5 and prepared:
                        sample_792.append(d.hex())

    print("=" * 60)
    print("=== carControl ===")
    print(f"  总帧数: {n_cc}")
    print(f"  latActive=True 帧数: {n_lat_active}  ({pct(n_lat_active, n_cc)})")
    print(f"  longActive=True 帧数: {n_long_active}  ({pct(n_long_active, n_cc)})")
    print(f"  torque!=0 帧数: {torque_nonzero}  ({pct(torque_nonzero, n_cc)})")
    print(f"  最大 torque (归一): {max_torque:.3f}")
    print(f"  最大 torqueOutputCan: {max_torque_can}")

    print("\n=== sendcan 790 (OP 发出的转向报文) ===")
    print(f"  790 总帧数: {n_790}")
    print(f"  LKAS_Active=1 帧数: {n_790_active}  ({pct(n_790_active, n_790)})")
    print(f"  LKAS_ReqPrepare=1 帧数: {n_790_reqprep}  ({pct(n_790_reqprep, n_790)})")
    if sample_790:
        print("  样例 (out, active, reqprep, hex):")
        for s in sample_790:
            print(f"    {s}")

    print("\n=== can 792 (真实 EPS 反馈, bus0) ===")
    print(f"  792 总帧数: {n_792}")
    print(f"  LKAS_Prepared=1 帧数: {n_792_prepared}  ({pct(n_792_prepared, n_792)})")
    if sample_792:
        print("  样例 (hex):")
        for s in sample_792:
            print(f"    {s}")

    print("\n" + "=" * 60)
    print("判读:")
    print("  - latActive 全程=0  -> OP 没激活横向 (问题在激活逻辑/MADS)")
    print("  - latActive>0 但 790 LKAS_Active 全0 -> carcontroller 没发激活扭矩")
    print("  - 790 LKAS_Active>0 但 792 LKAS_Prepared 全0")
    print("      -> EPS 不响应握手 (扭矩/状态/校验和/总线方向问题)")
    print("  - 792 LKAS_Prepared>0 但车不转 -> 扭矩被 EPS 接受但量级/方向问题")
    print("=" * 60)


def pct(a, b):
    return f"{100.0*a/b:.1f}%" if b else "0%"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python3 analyze_rlog_lat.py <segment目录或rlog文件>")
        print("先运行: ls -lt /data/media/0/realdata/ | head  找到最近的 segment")
        sys.exit(1)
    main(sys.argv[1])
