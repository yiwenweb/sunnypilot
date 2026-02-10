#!/usr/bin/env python3
"""启用 MADS 参数 — 让 ACC 开关直接激活横向控制"""
from openpilot.common.params import Params

params = Params()

# 启用 MADS
params.put_bool("Mads", True)
# 允许通过 ACC 主开关激活 MADS
params.put_bool("MadsMainCruiseAllowed", True)
# 启用统一 engagement 模式
params.put_bool("MadsUnifiedEngagementMode", True)
# 确保 openpilot 控制已启用
params.put_bool("OpenpilotEnabledToggle", True)

print("=== MADS 参数已设置 ===")
print(f"  Mads = {params.get_bool('Mads')}")
print(f"  MadsMainCruiseAllowed = {params.get_bool('MadsMainCruiseAllowed')}")
print(f"  MadsUnifiedEngagementMode = {params.get_bool('MadsUnifiedEngagementMode')}")
print(f"  OpenpilotEnabledToggle = {params.get_bool('OpenpilotEnabledToggle')}")
print()
print("请重启 openpilot: sudo reboot -f")
