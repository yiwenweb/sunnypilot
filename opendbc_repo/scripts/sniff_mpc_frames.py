#!/usr/bin/env python3
"""
BYD 原厂 MPC 帧抓取工具

抓取 Bus 2 上原厂 MPC 发送的 790/813/814/815 真实帧数据，
以及 Bus 0 上 openpilot 发送的对应帧（如果有），用于对比分析。

目的：找出 openpilot 生成的帧和原厂帧的差异，
      解决"请检查多功能视频控制器/毫米波雷达"报错。

使用方法（在 C3 上运行，ACC 关闭状态）：
  pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 2
  python3 opendbc_repo/scripts/sniff_mpc_frames.py

  或者在 openpilot 运行时抓取（可以对比 OP 帧和原厂帧）：
  python3 opendbc_repo/scripts/sniff_mpc_frames.py

操作：
  1. 先不按 ACC，等 5 秒抓原厂 MPC 空闲帧
  2. 按 ACC 开启，等 5 秒抓原厂 MPC 激活帧
  3. Ctrl+C 结束，查看报告
"""

import time
import cereal.messaging as messaging

TARGET_ADDRS = {
    790: "ACC_MPC_STATE",
    792: "ACC_EPS_STATE",
    813: "ACC_HUD_ADAS",
    814: "ACC_CMD",
    815: "ACC_AEB",
}

def decode_790(data: bytes) -> dict:
    """解码 790 ACC_MPC_STATE"""
    b = data
    return {
        "AutoFullBeamState": (b[0] >> 0) & 0xF,
        "LeftLaneState": (b[0] >> 4) & 0x3,
        "LKAS_Config": (b[0] >> 6) & 0x3,
        "SETME2_0x1": (b[1] >> 0) & 0x3,
        "ReqHandsOnSteeringWheel": (b[1] >> 2) & 0x1,
        "MPC_State": (b[1] >> 3) & 0xF,
        "AutoFullBeam_OnOff": (b[1] >> 7) & 0x1,
        "LKAS_Output_raw": (b[2] | (b[3] << 8)) & 0x7FF,
        "LKAS_Output": ((b[2] | (b[3] << 8)) & 0x7FF) - 2048 if ((b[2] | (b[3] << 8)) & 0x7FF) > 1023 else (b[2] | (b[3] << 8)) & 0x7FF,
        "LKAS_ReqPrepare": (b[3] >> 3) & 0x1,
        "LKAS_Active": (b[3] >> 4) & 0x1,
        "SETME3_0x0": (b[3] >> 5) & 0x1,
        "TrafficSignRecognition_OnOff": (b[3] >> 6) & 0x1,
        "SETME4_0x0": (b[3] >> 7) & 0x1,
        "SETME5_0x1": (b[4] >> 0) & 0x3,
        "RightLaneState": (b[4] >> 2) & 0x3,
        "LKAS_State": (b[4] >> 4) & 0xF,
        "TrafficSignRecognition_Result_raw": b[5],
        "LKAS_AlarmType": (b[6] >> 0) & 0x3,
        "SETME7_0x3": (b[6] >> 2) & 0x3,
        "COUNTER": (b[6] >> 4) & 0xF,
        "CHECKSUM": b[7],
    }

def decode_813(data: bytes) -> dict:
    """解码 813 ACC_HUD_ADAS"""
    b = data
    return {
        "SetSpeed_raw": (b[0] | ((b[1] & 0x1) << 8)),
        "SetSpeed": (b[0] | ((b[1] & 0x1) << 8)) * 0.5,
        "HasLead": (b[1] >> 1) & 0x1,
        "SetDistance": (b[1] >> 2) & 0x7,
        "LeadingDistance": (b[1] >> 5) & 0x7,
        "AEB": (b[2] >> 0) & 0x1,
        "FCW": (b[2] >> 1) & 0x1,
        "SETME1_0x1": (b[2] >> 2) & 0x1,
        "AccState": (b[2] >> 3) & 0x7,
        "AccOn1": (b[2] >> 6) & 0x1,
        "CloseWarning": (b[2] >> 7) & 0x1,
        "SETME2_0x1": (b[3] >> 0) & 0x1,
        "Notify": (b[3] >> 1) & 0x7F,
        "Status": (b[4] >> 0) & 0xF,
        "SETME3_0xFFF_raw": ((b[4] >> 4) & 0xF) | (b[5] << 4),
        "COUNTER": (b[6] >> 0) & 0xF,
        "SETME4_0xF": (b[6] >> 4) & 0xF,
        "CHECKSUM": b[7],
    }

def decode_814(data: bytes) -> dict:
    """解码 814 ACC_CMD"""
    b = data
    accel_raw = b[0]
    return {
        "AccelCmd_raw": accel_raw,
        "AccelCmd": accel_raw * 0.05 - 5,
        "ComfortBandUpper_raw": b[1],
        "ComfortBandUpper": b[1] * 0.05 - 5,
        "ComfortBandLower_raw": b[2],
        "ComfortBandLower": b[2] * 0.05 - 5,
        "JerkUpperLimit_raw": b[3] & 0x7F,
        "JerkUpperLimit": (b[3] & 0x7F) * 0.2,
        "SETME1_0x1": (b[3] >> 7) & 0x1,
        "JerkLowerLimit_raw": b[4] & 0x7F,
        "JerkLowerLimit": (b[4] & 0x7F) * 0.2 - 16,
        "ResumeFromStandstill": (b[4] >> 7) & 0x1,
        "StandstillState": (b[5] >> 0) & 0x1,
        "BrakeBehaviour": (b[5] >> 1) & 0x3,
        "AccReqNotStandstill": (b[5] >> 3) & 0x1,
        "AccControlActive": (b[5] >> 4) & 0x1,
        "AccOverrideOrStandstill": (b[5] >> 5) & 0x1,
        "EspBehaviour": (b[5] >> 6) & 0x3,
        "COUNTER": (b[6] >> 0) & 0xF,
        "SETME2_0xF": (b[6] >> 4) & 0xF,
        "CHECKSUM": b[7],
    }

def decode_815(data: bytes) -> dict:
    """解码 815 ACC_AEB"""
    b = data
    return {
        "byte0": b[0],
        "AEB_Active": b[0] & 0x1,
        "byte1": b[1],
        "AEB_Decel_raw": b[1],
        "AEB_Decel": b[1] * 0.05,
        "byte2": b[2],
        "byte3": b[3],
        "byte4": b[4],
        "byte5": b[5],
        "COUNTER": (b[6] >> 0) & 0xF,
        "SETME_0xF": (b[6] >> 4) & 0xF,
        "CHECKSUM": b[7],
    }

DECODERS = {
    790: decode_790,
    813: decode_813,
    814: decode_814,
    815: decode_815,
}


def verify_checksum(data: bytes) -> bool:
    """验证原厂补码校验和"""
    sum_7 = sum(data[:7])
    expected = (0x100 - sum_7 % 0x100) & 0xFF
    return data[7] == expected


def main():
    sm = messaging.SubMaster(['can'])

    # frames[bus][addr] = list of (timestamp, raw_bytes)
    frames: dict[int, dict[int, list]] = {0: {}, 2: {}}

    print("=" * 80)
    print("BYD 原厂 MPC 帧抓取工具")
    print("抓取 Bus 2 (原厂MPC) 和 Bus 0 (ECU/openpilot) 的 790/813/814/815 帧")
    print("=" * 80)
    print()
    print("操作步骤:")
    print("  1. 先不按 ACC，等待抓取原厂空闲帧")
    print("  2. 按 ACC 开启，抓取激活帧")
    print("  3. Ctrl+C 结束查看报告")
    print()

    start_time = time.monotonic()
    last_print = start_time

    try:
        while True:
            sm.update(100)

            if sm.updated['can']:
                now = time.monotonic() - start_time
                for msg in sm['can']:
                    bus = msg.src
                    addr = msg.address

                    if addr not in TARGET_ADDRS:
                        continue
                    if bus not in (0, 2):
                        continue

                    if addr not in frames[bus]:
                        frames[bus][addr] = []

                    # 保存前 200 帧和最后 200 帧
                    entry = (now, bytes(msg.dat))
                    if len(frames[bus][addr]) < 200:
                        frames[bus][addr].append(entry)
                    else:
                        # 保留前100帧，替换后100帧
                        if len(frames[bus][addr]) == 200:
                            frames[bus][addr] = frames[bus][addr][:100]
                        if len(frames[bus][addr]) < 200:
                            frames[bus][addr].append(entry)
                        else:
                            frames[bus][addr][-1] = entry

                # 每 5 秒打印状态
                elapsed = time.monotonic() - start_time
                if elapsed - (last_print - start_time) >= 5.0:
                    print(f"\n--- {elapsed:.0f}s ---")
                    for bus in (0, 2):
                        bus_label = "Bus 0 (ECU/OP)" if bus == 0 else "Bus 2 (原厂MPC)"
                        for addr in sorted(TARGET_ADDRS.keys()):
                            if addr in frames[bus]:
                                n = len(frames[bus][addr])
                                last_data = frames[bus][addr][-1][1]
                                chk_ok = "✓" if verify_checksum(last_data) else "✗"
                                print(f"  {bus_label} {TARGET_ADDRS[addr]:>16}({addr}): {n:>4}帧  "
                                      f"最新={last_data.hex(' ')}  校验{chk_ok}")
                    last_print = time.monotonic()

    except KeyboardInterrupt:
        pass

    elapsed = time.monotonic() - start_time
    if elapsed < 2:
        print("运行时间太短")
        return

    # ==================== 详细报告 ====================
    print("\n" + "=" * 80)
    print(f"原厂 MPC 帧分析报告 (运行 {elapsed:.1f} 秒)")
    print("=" * 80)

    for addr in sorted(TARGET_ADDRS.keys()):
        name = TARGET_ADDRS[addr]
        print(f"\n{'='*80}")
        print(f"  {name} ({addr})")
        print(f"{'='*80}")

        for bus in (2, 0):
            bus_label = "Bus 2 (原厂MPC)" if bus == 2 else "Bus 0 (ECU/OP)"

            if addr not in frames[bus] or not frames[bus][addr]:
                print(f"\n  [{bus_label}] 未收到")
                continue

            flist = frames[bus][addr]
            print(f"\n  [{bus_label}] 共 {len(flist)} 帧")

            # 打印前 5 帧和后 5 帧的原始数据
            show_frames = flist[:5] + (flist[-5:] if len(flist) > 5 else [])
            if len(flist) > 5:
                print(f"  --- 前5帧 ---")

            for i, (ts, data) in enumerate(show_frames):
                if i == 5 and len(flist) > 5:
                    print(f"  --- 后5帧 ---")
                chk_ok = "✓" if verify_checksum(data) else "✗"
                print(f"    [{ts:7.2f}s] {data.hex(' ')}  校验{chk_ok}")

            # 解码第一帧和最后一帧
            if addr in DECODERS:
                decoder = DECODERS[addr]
                print(f"\n  首帧解码:")
                first_decoded = decoder(flist[0][1])
                for k, v in first_decoded.items():
                    print(f"    {k:>35} = {v}")

                if len(flist) > 1:
                    print(f"\n  末帧解码:")
                    last_decoded = decoder(flist[-1][1])
                    for k, v in last_decoded.items():
                        if v != first_decoded[k]:
                            print(f"    {k:>35} = {v}  (首帧={first_decoded[k]})")
                        else:
                            print(f"    {k:>35} = {v}")

            # 校验和统计
            chk_pass = sum(1 for _, d in flist if verify_checksum(d))
            chk_fail = len(flist) - chk_pass
            print(f"\n  校验和: {chk_pass}/{len(flist)} 通过"
                  f"{f', {chk_fail} 失败!' if chk_fail else ''}")

            # 找出所有不变的字节位置
            if len(flist) > 1:
                constant_bytes = []
                for byte_idx in range(min(8, len(flist[0][1]))):
                    vals = set(d[byte_idx] for _, d in flist)
                    if len(vals) == 1:
                        constant_bytes.append((byte_idx, list(vals)[0]))
                if constant_bytes:
                    print(f"  固定字节: {', '.join(f'byte[{i}]=0x{v:02X}' for i, v in constant_bytes)}")

    # ==================== 对比分析 ====================
    print(f"\n{'='*80}")
    print("  Bus 2 vs Bus 0 对比 (原厂 vs openpilot)")
    print(f"{'='*80}")

    for addr in sorted(TARGET_ADDRS.keys()):
        if addr == 792:
            continue  # 792 方向不同，不对比
        name = TARGET_ADDRS[addr]
        has_bus2 = addr in frames[2] and frames[2][addr]
        has_bus0 = addr in frames[0] and frames[0][addr]

        if has_bus2 and has_bus0:
            d2 = frames[2][addr][0][1]
            d0 = frames[0][addr][0][1]
            diffs = []
            for i in range(min(len(d2), len(d0))):
                if d2[i] != d0[i]:
                    diffs.append(f"byte[{i}]: 原厂=0x{d2[i]:02X} vs OP=0x{d0[i]:02X}")
            if diffs:
                print(f"\n  {name} ({addr}) - 有差异:")
                print(f"    原厂: {d2.hex(' ')}")
                print(f"    OP:   {d0.hex(' ')}")
                for d in diffs:
                    print(f"    {d}")
            else:
                print(f"\n  {name} ({addr}) - 完全一致 ✓")
        elif has_bus2 and not has_bus0:
            print(f"\n  {name} ({addr}) - 仅原厂有 (Bus 0 无 OP 帧)")
        elif has_bus0 and not has_bus2:
            print(f"\n  {name} ({addr}) - 仅 OP 有 (Bus 2 无原厂帧)")

    print("\n" + "=" * 80)
    print("请把以上输出截图发给开发者!")
    print("重点关注: 原厂帧和 OP 帧的字节差异、校验和是否正确")
    print("=" * 80)


if __name__ == "__main__":
    main()
