#!/usr/bin/env python3
"""
诊断工具: 直接读取 panda 安全层状态
验证 controls_allowed 是否被正确设置

用法: 先停掉 openpilot，然后运行
  pkill -f selfdrive.manager
  sleep 3
  python3 diag_panda_safety.py

这个脚本直接通过 panda USB API 读取安全层状态，
不依赖 cereal/openpilot，可以独立验证 byd.h 逻辑
"""

import time
import sys

sys.path.insert(0, '/data/openpilot/panda')
from panda import Panda

def main():
    print("=" * 70)
    print("BYD Panda 安全层状态诊断")
    print("=" * 70)
    print("注意: 需要先停掉 openpilot (pkill -f selfdrive.manager)")
    print("按各个按钮观察 controls_allowed 变化")
    print("-" * 70)

    p = Panda()

    # 设置安全模式为 BYD (35)
    # 需要先设置 alternative_experience 启用 MADS
    print(f"Panda FW: {p.get_version()}")

    h = p.health()
    print(f"当前安全模式: {h['safety_mode']}, controls_allowed: {h['controls_allowed']}")
    print()

    prev_state = None
    last_print = 0

    # 读取 944 的原始 CAN 数据并同时查询 panda health
    while True:
        # 读取 CAN 消息
        msgs = p.can_recv()

        btn_info = ""
        for addr, _, dat, bus in msgs:
            if addr == 944 and bus == 0 and len(dat) >= 2:
                acc_updown = (dat[0] >> 3) & 0x3
                cancel = (dat[0] >> 6) & 0x1
                acc_onoff = (dat[1] >> 0) & 0x1
                btn_info = f"AccUpDown={acc_updown} Cancel={cancel} ACC_OnOff={acc_onoff}"

        now = time.monotonic()
        if (now - last_print) > 0.5:
            h = p.health()
            ca = h['controls_allowed']

            state = (ca, btn_info)
            changed = ""
            if prev_state and state != prev_state:
                changed = " *** CHANGED ***"

            if btn_info:
                print(f"[{now:.1f}] controls_allowed={ca} safety_mode={h['safety_mode']} | {btn_info}{changed}")
            else:
                print(f"[{now:.1f}] controls_allowed={ca} safety_mode={h['safety_mode']}{changed}")

            prev_state = state
            last_print = now

        time.sleep(0.05)


if __name__ == "__main__":
    main()
