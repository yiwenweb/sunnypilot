#!/usr/bin/env python3
"""在 openpilot 运行时检查 panda 状态和 CAN 转发情况（不杀进程）"""
from cereal import messaging
import time

sm = messaging.SubMaster(['pandaStates', 'carState'])
printed = set()

print("=== openpilot 运行时 panda 状态 ===")
for i in range(30):
    sm.update(1000)
    if sm.updated['pandaStates'] and 'ps' not in printed:
        for j, ps in enumerate(sm['pandaStates']):
            print(f"panda[{j}]:")
            print(f"  safetyModel={ps.safetyModel}")
            print(f"  safetyParam={ps.safetyParam}")
            print(f"  controlsAllowed={ps.controlsAllowed}")
            print(f"  ignitionLine={ps.ignitionLine}")
            print(f"  ignitionCan={ps.ignitionCan}")
            print(f"  faultStatus={ps.faultStatus}")
            print(f"  harnessStatus={ps.harnessStatus}")
            print(f"  heartbeatLost={ps.heartbeatLost}")
            print(f"  canRxErrs={ps.canState0.busOff if hasattr(ps, 'canState0') else 'N/A'}")
        printed.add('ps')
    if sm.updated['carState'] and 'cs' not in printed:
        cs = sm['carState']
        print(f"\ncarState:")
        print(f"  canValid={cs.canValid}")
        print(f"  canTimeout={cs.canTimeout}")
        print(f"  canErrorCounter={cs.canErrorCounter}")
        printed.add('cs')
    if len(printed) >= 2:
        break
    time.sleep(0.3)

if not printed:
    print("超时: 未收到消息")
