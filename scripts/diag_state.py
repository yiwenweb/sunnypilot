#!/usr/bin/env python3
"""诊断 openpilot 当前状态"""
from cereal import messaging
import time

sm = messaging.SubMaster(['selfdriveState', 'carState', 'livePose'])
for i in range(30):
    sm.update(1000)
    if sm.updated['selfdriveState']:
        ss = sm['selfdriveState']
        print(f"state={ss.state}")
        print(f"enabled={ss.enabled}")
        print(f"active={ss.active}")
        print(f"alertText1={ss.alertText1}")
        print(f"alertText2={ss.alertText2}")
        print(f"alertType={ss.alertType}")
        print(f"alertStatus={ss.alertStatus}")
    if sm.updated['carState']:
        cs = sm['carState']
        print(f"cruiseAvail={cs.cruiseState.available}")
        print(f"cruiseEnabled={cs.cruiseState.enabled}")
        print(f"vEgo={cs.vEgo:.1f}")
        print(f"steerFaultTemp={cs.steerFaultTemporary}")
        print(f"steerFaultPerm={cs.steerFaultPermanent}")
        print(f"canValid={cs.canValid}")
    if sm.updated['livePose']:
        lp = sm['livePose']
        print(f"inputsOK={lp.inputsOK}")
        print(f"posenetOK={lp.posenetOK}")
        print(f"sensorsOK={lp.sensorsOK}")
    if sm.updated['selfdriveState']:
        break
    time.sleep(0.5)
else:
    print("超时: 未收到 selfdriveState")
