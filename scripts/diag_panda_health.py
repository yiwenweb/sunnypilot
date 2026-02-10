#!/usr/bin/env python3
"""直接查询 panda health — 不需要停 openpilot
检查 alternative_experience 是否包含 ENABLE_MADS (1024)

用法: python3 /data/openpilot/scripts/diag_panda_health.py
"""
import cereal.messaging as messaging
import time

# 方法1: 通过 cereal 读取 pandaStates
sm = messaging.SubMaster(['pandaStates', 'carParams'])
print("=== 通过 cereal 读取 panda 状态 ===")
for i in range(20):
    sm.update(500)
    if sm.updated['pandaStates']:
        for j, ps in enumerate(sm['pandaStates']):
            print(f"PANDA[{j}]:")
            print(f"  safetyModel = {ps.safetyModel}")
            print(f"  safetyParam = {ps.safetyParam}")
            print(f"  alternativeExperience = {ps.alternativeExperience}")
            print(f"  ENABLE_MADS = {bool(ps.alternativeExperience & 1024)}")
            print(f"  controlsAllowed = {ps.controlsAllowed}")
            print(f"  harnessStatus = {ps.harnessStatus}")
            print(f"  faultStatus = {ps.faultStatus}")
            print(f"  heartbeatLost = {ps.heartbeatLost}")
        break
    if i == 19:
        print("pandaStates 未收到！")

for i in range(20):
    sm.update(500)
    if sm.updated['carParams']:
        cp = sm['carParams']
        print(f"\nCAR PARAMS:")
        print(f"  alternativeExperience = {cp.alternativeExperience}")
        print(f"  ENABLE_MADS = {bool(cp.alternativeExperience & 1024)}")
        print(f"  pcmCruise = {cp.pcmCruise}")
        for k, s in enumerate(cp.safetyConfigs):
            print(f"  safetyConfig[{k}]: model={s.safetyModel} param={s.safetyParam}")
        break
    if i == 19:
        print("carParams 未收到！")

print("\ndone")
