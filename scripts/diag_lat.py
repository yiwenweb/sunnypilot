#!/usr/bin/env python3
"""诊断横向控制状态 — 确认 latActive 和 MADS 状态"""
import cereal.messaging as messaging
from openpilot.common.params import Params

params = Params()
print("=== 参数检查 ===")
print(f"  Mads = {params.get_bool('Mads')}")
print(f"  MadsMainCruiseAllowed = {params.get_bool('MadsMainCruiseAllowed')}")
print(f"  MadsUnifiedEngagementMode = {params.get_bool('MadsUnifiedEngagementMode')}")
print(f"  OpenpilotEnabledToggle = {params.get_bool('OpenpilotEnabledToggle')}")
print()

sm = messaging.SubMaster(['selfdriveState', 'carState', 'carControl', 'controlsState',
                           'selfdriveStateSP', 'pandaStates', 'onroadEvents', 'onroadEventsSP'])
print("=== 等待数据 (挂D档行驶+按ACC后观察) ===")
for i in range(200):
    sm.update(1000)
    if not sm.updated['carState']:
        continue

    cs = sm['carState']
    ss = sm['selfdriveState']
    cc = sm['carControl']
    ss_sp = sm['selfdriveStateSP']
    mads = ss_sp.mads

    print(f"\n--- tick {i} ---")
    print(f"  cruise: avail={cs.cruiseState.available} enabled={cs.cruiseState.enabled}")
    print(f"  selfdrive: state={ss.state} enabled={ss.enabled} active={ss.active}")
    print(f"  MADS: avail={mads.available} active={mads.active} enabled={mads.enabled} state={mads.state}")
    print(f"  carControl: latActive={cc.latActive} longActive={cc.longActive}")
    print(f"  vEgo={cs.vEgo:.1f} gear={cs.gearShifter} standstill={cs.standstill}")
    print(f"  steerFault: temp={cs.steerFaultTemporary} perm={cs.steerFaultPermanent}")
    print(f"  steeringPressed={cs.steeringPressed} brakePressed={cs.brakePressed}")
    print(f"  parkingBrake={cs.parkingBrake} doorOpen={cs.doorOpen} seatbelt={cs.seatbeltUnlatched}")

    if cc.latActive:
        print(f"  actuators: torque={cc.actuators.torque:.3f} angle={cc.actuators.steeringAngleDeg:.1f}")

    if sm.updated['pandaStates']:
        for ps in sm['pandaStates']:
            print(f"  panda: controlsAllowed={ps.controlsAllowed}")

    # 显示 onroad events
    if sm.updated['onroadEvents']:
        evts = sm['onroadEvents']
        if evts:
            names = [str(e.name) for e in evts]
            print(f"  events: {names}")

    if sm.updated['onroadEventsSP']:
        evts_sp = sm['onroadEventsSP']
        if evts_sp:
            names_sp = [str(e.name) for e in evts_sp]
            print(f"  events_sp: {names_sp}")

    # 按钮事件
    if cs.buttonEvents:
        for be in cs.buttonEvents:
            print(f"  BUTTON: type={be.type} pressed={be.pressed}")

print("done")
