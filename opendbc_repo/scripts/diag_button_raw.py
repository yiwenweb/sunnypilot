#!/usr/bin/env python3
"""
诊断工具: 读取 PCM_BUTTONS (944) 原始 CAN 字节
按各个按钮，观察哪些 bit 变化

用法: python3 diag_button_raw.py
"""

import cereal.messaging as messaging
import time

def main():
    sm = messaging.SubMaster(['can'])

    print("=" * 78)
    print("BYD PCM_BUTTONS (944) 原始字节诊断")
    print("=" * 78)
    print("按各个按钮观察变化。重点关注 byte0 和 byte1")
    print("-" * 78)

    prev_dat = None
    last_print = 0

    while True:
        sm.update(100)
        if not sm.updated['can']:
            continue

        for msg in sm['can']:
            if msg.address == 944 and msg.src == 0:
                dat = bytes(msg.dat)
                if len(dat) < 8:
                    continue

                now = time.monotonic()
                # 只在数据变化或每3秒打印
                # 忽略 byte6/7 (counter/checksum) 的变化
                dat_key = dat[:6]
                prev_key = prev_dat[:6] if prev_dat else None

                if dat_key != prev_key or (now - last_print) > 3.0:
                    changed = ""
                    if prev_dat and dat_key != prev_key:
                        changed = " *** CHANGED ***"

                    print(f"\n[{now:.1f}]{changed}")
                    print(f"  RAW: {' '.join(f'{b:02X}' for b in dat)}")
                    print(f"  BIN: byte0={dat[0]:08b}  byte1={dat[1]:08b}  byte2={dat[2]:08b}")

                    # 当前 byd.h 提取方式
                    cur_updown = (dat[0] >> 3) & 0x3
                    cur_cancel = (dat[0] >> 6) & 0x1
                    cur_acconoff = (dat[1] >> 0) & 0x1
                    print(f"  当前byd.h: AccUpDown={(dat[0]>>3)&3} Cancel={(dat[0]>>6)&1} ACC_OnOff={(dat[1]>>0)&1}")

                    # 所有可能的 2-bit 提取 (byte0)
                    print(f"  byte0 所有2bit: ", end="")
                    for shift in range(7):
                        val = (dat[0] >> shift) & 0x3
                        print(f"b{shift+1}:{shift}={val} ", end="")
                    print()

                    # 所有可能的 1-bit 提取 (byte0)
                    print(f"  byte0 所有1bit: ", end="")
                    for bit in range(8):
                        val = (dat[0] >> bit) & 0x1
                        print(f"b{bit}={val} ", end="")
                    print()

                    # byte1 所有 1-bit
                    print(f"  byte1 所有1bit: ", end="")
                    for bit in range(8):
                        val = (dat[1] >> bit) & 0x1
                        print(f"b{bit}={val} ", end="")
                    print()

                    prev_dat = dat
                    last_print = now


if __name__ == "__main__":
    main()
