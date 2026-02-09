#!/usr/bin/env python3
"""诊断 openpilot 当前状态"""
from cereal import messaging
import time

sm = messaging.SubMaster(['selfdriveState', 'carState', 'livePose'])
printed = set()
for i in range(100):
    sm.update(1000)
    if sm.updated['selfdriveState'] and 'ss' not in printed:
        ss = sm['selfdriveState']
        print(f"--- selfdriveState ---")
        print(f"state={ss.state} enabled={ss.enabled} active={ss.active}")
        print(f"alertText1={ss.alertText1}")
        print(f"alertText2={ss.alertText2}")
        print(f"alertType={ss.alertType}")
        printed.add('ss')
    if sm.updated['carState'] and 'cs' not in printed:
        cs = sm['carState']
        print(f"--- carState ---")
        print(f"cruiseAvail={cs.cruiseState.available} cruiseEnabled={cs.cruiseState.enabled}")
        print(f"vEgo={cs.vEgo:.1f} canValid={cs.canValid}")
        print(f"steerFaultTemp={cs.steerFaultTemporary} steerFaultPerm={cs.steerFaultPermanent}")
        print(f"gasPressed={cs.gasPressed} brakePressed={cs.brakePressed}")
        print(f"gearShifter={cs.gearShifter}")
        evts = [str(e.name) for e in cs.events]
        print(f"events={evts}")
        printed.add('cs')
    if sm.updated['livePose'] and 'lp' not in printed:
        lp = sm['livePose']
        print(f"--- livePose ---")
        print(f"inputsOK={lp.inputsOK} posenetOK={lp.posenetOK} sensorsOK={lp.sensorsOK}")
        printed.add('lp')
    if len(printed) >= 3:
        break
    time.sleep(0.2)
if not printed:
    print("超时: 未收到任何消息")
