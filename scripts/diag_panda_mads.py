#!/usr/bin/env python3
"""检查 panda 的 MADS 状态和 controls_allowed_lat"""
import cereal.messaging as messaging

sm = messaging.SubMaster(['pandaStates', 'carParams'])
print("=== 检查 panda MADS 状态 ===")
for i in range(30):
    sm.update(1000)
    if sm.updated['pandaStates']:
        for ps in sm['pandaStates']:
            print(f"  panda: safetyModel={ps.safetyModel} safetyParam={ps.safetyParam}")
            print(f"         alternativeExperience={ps.alternativeExperience}")
            print(f"         controlsAllowed={ps.controlsAllowed}")
            print(f"         harnessStatus={ps.harnessStatus}")
    if sm.updated['carParams']:
        cp = sm['carParams']
        print(f"  carParams: alternativeExperience={cp.alternativeExperience}")
        print(f"             pcmCruise={cp.pcmCruise}")
        print(f"             openpilotLongitudinalControl={cp.openpilotLongitudinalControl}")
        break

print("done")
