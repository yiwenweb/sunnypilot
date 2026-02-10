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
print(f"  DisengageOnAccelerator = {params.get_bool('DisengageOnAccelerator')}")
print()

sm = messaging.SubMaster(['selfdriveState', 'carState', 'carControl', 'controlsState',
                           'selfdriveStateSP', 'pandaStates'])
print("=== 等待数据 (按ACC开关后观察) ===")
for i in range(100):
    sm.update(1000)
    if not sm.updated['carState']:
        continue

    cs = sm['carState']
    ss = sm['selfdriveState']
    cc = sm['carControl']
    ss_sp = sm['selfdriveStateSP']

    mads = ss_sp.mads if hasattr(ss_sp, 'mads') else None

    print(f"\n--- tick {i} ---")
    print(f"  cruiseState: available={cs.cruiseState.available} enabled={cs.cruiseState.enabled}")
    print(f"  selfdriveState: state={ss.state} enabled={ss.enabled} active={ss.active}")
    if mads:
        print(f"  MADS: available={mads.available} active={mads.active} enabled={mads.enabled} state={mads.state}")
    print(f"  carControl: latActive={cc.latActive} longActive={cc.longActive}")
    print(f"  vEgo={cs.vEgo:.1f} gear={cs.gearShifter} standstill={cs.standstill}")
    print(f"  steerFaultTemp={cs.steerFaultTemporary} steerFaultPerm={cs.steerFaultPermanent}")
    print(f"  steeringPressed={cs.steeringPressed} brakePressed={cs.brakePressed}")

    if sm.updated['pandaStates']:
        for ps in sm['pandaStates']:
            print(f"  panda: controlsAllowed={ps.controlsAllowed}")

    if sm.updated['controlsState']:
        cts = sm['controlsState']
        print(f"  controlsState: lateralType={cts.lateralControlState.which()}")

    # 检查按钮事件
    if cs.buttonEvents:
        for be in cs.buttonEvents:
            print(f"  BUTTON: type={be.type} pressed={be.pressed}")

print("done")
