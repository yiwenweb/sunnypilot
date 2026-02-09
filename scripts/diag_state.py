#!/usr/bin/env python3
"""诊断 openpilot 当前状态 - v3"""
from cereal import messaging
import time
import subprocess

# 检查关键进程是否在运行
print("=== 进程检查 ===")
result = subprocess.run(['pgrep', '-af', 'card|selfdrive|pandad|locationd'], capture_output=True, text=True)
print(result.stdout if result.stdout else "没有找到相关进程")

print("\n=== 消息检查 ===")
sm = messaging.SubMaster(['selfdriveState', 'carState', 'livePose', 'pandaStates', 'carParams'])
printed = set()
for i in range(60):
    sm.update(500)
    for svc in ['selfdriveState', 'carState', 'livePose', 'pandaStates', 'carParams']:
        if sm.updated[svc] and svc not in printed:
            print(f"\n--- {svc} (frame={sm.recv_frame[svc]}, valid={sm.valid[svc]}) ---")
            if svc == 'selfdriveState':
                ss = sm[svc]
                print(f"  state={ss.state} enabled={ss.enabled} active={ss.active}")
                print(f"  alertText1={ss.alertText1}")
                print(f"  alertType={ss.alertType}")
            elif svc == 'carState':
                cs = sm[svc]
                print(f"  cruiseAvail={cs.cruiseState.available} cruiseEnabled={cs.cruiseState.enabled}")
                print(f"  vEgo={cs.vEgo:.1f} canValid={cs.canValid}")
                print(f"  steerFaultTemp={cs.steerFaultTemporary} steerFaultPerm={cs.steerFaultPermanent}")
                print(f"  gearShifter={cs.gearShifter}")
            elif svc == 'livePose':
                lp = sm[svc]
                print(f"  inputsOK={lp.inputsOK} posenetOK={lp.posenetOK} sensorsOK={lp.sensorsOK}")
            elif svc == 'pandaStates':
                for j, ps in enumerate(sm[svc]):
                    print(f"  panda[{j}]: safety={ps.safetyModel} ignLine={ps.ignitionLine} ignCan={ps.ignitionCan}")
            elif svc == 'carParams':
                cp = sm[svc]
                print(f"  brand={cp.brand} carFingerprint={cp.carFingerprint}")
                print(f"  openpilotLongitudinalControl={cp.openpilotLongitudinalControl}")
                print(f"  pcmCruise={cp.pcmCruise}")
            printed.add(svc)
    if len(printed) >= 5:
        break
    time.sleep(0.2)

missing = set(['selfdriveState', 'carState', 'livePose', 'pandaStates', 'carParams']) - printed
if missing:
    print(f"\n未收到: {missing}")
    for svc in missing:
        print(f"  {svc}: recv_frame={sm.recv_frame[svc]} valid={sm.valid[svc]}")
