#!/usr/bin/env python3
"""
诊断工具: 验证 PCM_BUTTONS (944) 按钮信号的原始字节提取
对比 CANParser 解析值 vs byd.h 中的原始字节提取逻辑

用法: python3 diag_button_bits.py
操作: 按各个按钮，观察 raw extraction 是否与 CANParser 一致

byd.h 中的提取逻辑:
  BTN_AccUpDown_Cmd: (msg->data[0] >> 3) & 0x3U
  BTN_AccCancel:     GET_BIT(msg, 6U) = (data[0] >> 6) & 1
  BTN_TOGGLE_ACC_OnOff: GET_BIT(msg, 8U) = (data[1] >> 0) & 1
"""

import cereal.messaging as messaging
import time

def main():
    sm = messaging.SubMaster(['can'])

    print("=" * 70)
    print("BYD PCM_BUTTONS (944) 按钮位提取验证")
    print("=" * 70)
    print("按各个按钮，对比 raw byte extraction vs CANParser")
    print("byd.h 提取:")
    print("  AccUpDown = (data[0] >> 3) & 0x3")
    print("  Cancel    = (data[0] >> 6) & 0x1")
    print("  ACC_OnOff = (data[1] >> 0) & 0x1")
    print("-" * 70)

    last_print = 0
    prev_raw = None

    while True:
        sm.update(100)
        if not sm.updated['can']:
            continue

        for msg in sm['can']:
            if msg.address == 944 and msg.src == 0:
                dat = bytes(msg.dat)
                if len(dat) < 8:
                    continue

                # Raw byte extraction (matching byd.h logic)
                raw_acc_updown = (dat[0] >> 3) & 0x3
                raw_cancel = (dat[0] >> 6) & 0x1
                raw_acc_onoff = (dat[1] >> 0) & 0x1

                # Also show full byte values for debugging
                raw_tuple = (raw_acc_updown, raw_cancel, raw_acc_onoff)

                now = time.monotonic()
                # Print on change or every 2 seconds
                if raw_tuple != prev_raw or (now - last_print) > 2.0:
                    b0 = dat[0]
                    b1 = dat[1]
                    print(f"[{now:.1f}] byte0=0x{b0:02X} ({b0:08b}) byte1=0x{b1:02X} ({b1:08b})")
                    print(f"  RAW: AccUpDown={raw_acc_updown} Cancel={raw_cancel} ACC_OnOff={raw_acc_onoff}")

                    # Also try alternative bit extractions for comparison
                    alt1 = (dat[0] >> 4) & 0x3  # bits 5:4
                    alt2 = (dat[0] >> 2) & 0x3  # bits 3:2
                    alt3 = dat[0] & 0x3          # bits 1:0
                    print(f"  ALT: bits5:4={alt1} bits3:2={alt2} bits1:0={alt3}")

                    prev_raw = raw_tuple
                    last_print = now

if __name__ == "__main__":
    main()
