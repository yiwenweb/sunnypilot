#!/usr/bin/env python3
"""
BYD 刹车信号诊断

检查 DRIVE_STATE (578) 的原始字节，确认 BrakePressed 信号位置。
DBC: BrakePressed : 37|1@0+ (Motorola bit 37)

操作: 先不踩刹车观察，再踩刹车观察，对比变化的 bit

使用方法:
  python3 /data/openpilot/opendbc_repo/scripts/diag_brake_signal.py
"""

import time
import cereal.messaging as messaging


def hex_str(data):
    return " ".join(f"{b:02x}" for b in data)


def bits_str(byte_val):
    return f"{byte_val:08b}"


def main():
    sm = messaging.SubMaster(['can', 'carState'])

    latest_578 = None
    latest_834 = None
    start = time.monotonic()
    last_report = 0

    print("=" * 80)
    print("BYD 刹车信号诊断 — DRIVE_STATE (578) 原始字节分析")
    print("=" * 80)
    print("操作: 先不踩刹车 → 再踩刹车 → 对比变化")
    print()
    print("DBC定义: BrakePressed : 37|1@0+ (Motorola)")
    print("GET_BIT(37) = byte[4] bit5 = byte[4] & 0x20")
    print()

    try:
        while True:
            sm.update(100)
            if not sm.updated['can']:
                continue

            now = time.monotonic() - start

            for msg in sm['can']:
                if msg.src == 0:
                    if msg.address == 578:
                        latest_578 = bytes(msg.dat)
                    elif msg.address == 834:
                        latest_834 = bytes(msg.dat)

            if now - last_report < 0.5:
                continue
            last_report = now

            brake_cs = ""
            if sm.valid['carState']:
                brake_cs = f"carState.brake={sm['carState'].brakePressed}"

            if latest_578:
                b = latest_578
                # GET_BIT(37) = byte[4] >> 5 & 1
                bit37_intel = (b[4] >> 5) & 1
                # 也检查其他可能的 brake bit 位置
                gear = b[5] & 0x7
                print(f"[{now:.1f}s] 578: {hex_str(b)}")
                print(f"  byte[4]={b[4]:02x}({bits_str(b[4])}) bit37(b4>>5)={bit37_intel}"
                      f"  byte[5]={b[5]:02x} gear={gear}")
                print(f"  所有byte的bit分析:")
                for i in range(8):
                    print(f"    byte[{i}]={b[i]:02x} = {bits_str(b[i])}")
                print(f"  {brake_cs}")

            if latest_834:
                b = latest_834
                print(f"  834 PEDAL: {hex_str(b)} AccPedal={b[0]*0.01:.2f} BrkPedal={b[1]*0.01:.2f}")

            print()

    except KeyboardInterrupt:
        print("\n诊断结束")


if __name__ == "__main__":
    main()
