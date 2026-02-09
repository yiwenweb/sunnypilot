#!/usr/bin/env python3
"""
BYD Panda 预初始化脚本
在 openpilot 启动前设置 panda 为 allOutput 模式，保持 Bus 0<->Bus 2 转发。
防止 pandad 初始化阶段（noOutput/silent）阻断原厂 MPC 消息导致 AEB 报错。

用法: 在 launch_openpilot.sh 中，在启动 openpilot 之前调用此脚本。
"""
import time
import sys

try:
    from panda import Panda

    serials = Panda.list()
    if not serials:
        print("panda_pre_init: 未找到 panda，跳过")
        sys.exit(0)

    for serial in serials:
        p = Panda(serial)
        # allOutput mode (1) 允许所有消息转发和发送
        p.set_safety_mode(1)
        print(f"panda_pre_init: {serial} 已设置为 allOutput 模式")
        p.close()

except Exception as e:
    print(f"panda_pre_init: 错误 - {e}")
    sys.exit(0)  # 不阻止 openpilot 启动
