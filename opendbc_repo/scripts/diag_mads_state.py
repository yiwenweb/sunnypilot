#!/usr/bin/env python3
"""诊断 MADS 横向控制状态 — 追踪为什么 latActive 不为 True

检查项:
1. selfdriveStateSP: mads.available, mads.enabled, mads.active, mads.state
2. selfdriveState: enabled, active, state
3. carControl: latActive, longActive
4. carState: cruiseState, steerFault, gear, standstill, doorOpen, seatbelt
5. onroadEvents: 所有活跃事件（找 NO_ENTRY 阻止原因）
6. panda: controls_allowed, controls_allowed_lat (MADS)

用法: openpilot 运行时 SSH 到 C3:
  python3 /data/openpilot/opendbc_repo/scripts/diag_mads_state.py
"""

import time
import cereal.messaging as messaging
from openpilot.common.params import Params
from cereal import log, custom

EventName = log.OnroadEvent.EventName
EventNameSP = custom.OnroadEventSP.EventName

# 事件名称映射（方便阅读）
def event_name(e):
    try:
        return EventName._enumerants.get(e.name, f"?{e.name}")
    except:
        return f"id={e.name}"

def main():
    params = Params()
    sm = messaging.SubMaster([
        'carState', 'carControl', 'selfdriveState', 'selfdriveStateSP',
        'onroadEvents', 'pandaStates',
    ])

    print("=" * 78)
    print("BYD MADS 横向控制诊断")
    print("=" * 78)

    # 打印关键参数
    for p in ["Mads", "MadsMainCruiseAllowed", "MadsUnifiedEngagementMode",
              "OpenpilotEnabledToggle", "DisengageOnAccelerator"]:
        v = params.get(p)
        if v is not None:
            try:
                print(f"  {p} = {v.decode()}")
            except:
                print(f"  {p} = {v}")
        else:
            print(f"  {p} = None")
    print()

    t0 = time.monotonic()
    prev_mads_state = None
    prev_mads_active = None
    prev_mads_enabled = None
    prev_lat_active = None
    prev_cruise_avail = None
    prev_ss_state = None
    prev_ss_enabled = None

    while True:
        sm.update(100)
        now = time.monotonic() - t0

        cs = sm['carState']
        cc = sm['carControl']
        ss = sm['selfdriveState']
        sp = sm['selfdriveStateSP']
        mads = sp.mads

        # 检测变化并打印
        changed = False

        if mads.state != prev_mads_state:
            print(f"[{now:.3f}s] MADS state: {prev_mads_state} -> {mads.state}")
            prev_mads_state = mads.state
            changed = True

        if mads.active != prev_mads_active:
            print(f"[{now:.3f}s] MADS active: {prev_mads_active} -> {mads.active}")
            prev_mads_active = mads.active
            changed = True

        if mads.enabled != prev_mads_enabled:
            print(f"[{now:.3f}s] MADS enabled: {prev_mads_enabled} -> {mads.enabled}")
            prev_mads_enabled = mads.enabled
            changed = True

        if cc.latActive != prev_lat_active:
            print(f"[{now:.3f}s] CC.latActive: {prev_lat_active} -> {cc.latActive}")
            prev_lat_active = cc.latActive
            changed = True

        if cs.cruiseState.available != prev_cruise_avail:
            print(f"[{now:.3f}s] cruiseAvail: {prev_cruise_avail} -> {cs.cruiseState.available}")
            prev_cruise_avail = cs.cruiseState.available
            changed = True

        if ss.state != prev_ss_state:
            print(f"[{now:.3f}s] SDS state: {prev_ss_state} -> {ss.state}")
            prev_ss_state = ss.state
            changed = True

        if ss.enabled != prev_ss_enabled:
            print(f"[{now:.3f}s] SDS enabled: {prev_ss_enabled} -> {ss.enabled}")
            prev_ss_enabled = ss.enabled
            changed = True

        if changed:
            # 打印当前完整状态
            print(f"  CS: vEgo={cs.vEgo:.1f} gear={cs.gearShifter} standstill={cs.standstill}"
                  f" brake={cs.brakePressed} steerFault=({cs.steerFaultTemporary},{cs.steerFaultPermanent})"
                  f" doorOpen={cs.doorOpen} seatbelt={cs.seatbeltUnlatched}")
            print(f"  MADS: avail={mads.available} enabled={mads.enabled} active={mads.active} state={mads.state}")
            print(f"  CC: latActive={cc.latActive} longActive={cc.longActive} enabled={cc.enabled}")
            print(f"  SDS: enabled={ss.enabled} active={ss.active} state={ss.state}")

            # 打印 onroadEvents
            if sm.valid['onroadEvents']:
                events = sm['onroadEvents']
                if len(events) > 0:
                    ev_strs = []
                    for e in events:
                        ev_strs.append(f"{e.name}({','.join(str(et) for et in [e.noEntry, e.softDisable, e.immediateDisable, e.enable, e.userDisable])})")
                    print(f"  Events: {', '.join(ev_strs)}")
                else:
                    print(f"  Events: (none)")

            # 打印 panda CA/CA_lat
            if sm.valid['pandaStates'] and len(sm['pandaStates']) > 0:
                ps = sm['pandaStates'][0]
                print(f"  Panda: CA={ps.controlsAllowed} safetyRxInvalid={ps.safetyRxInvalid}")

            # 打印按钮事件
            if len(cs.buttonEvents) > 0:
                for be in cs.buttonEvents:
                    print(f"  Button: type={be.type} pressed={be.pressed}")
            print()

        # 每3秒打印一次摘要
        if int(now) % 3 == 0 and int(now * 10) % 30 == 0:
            print(f"[{now:.0f}s] MADS={mads.state}(en={mads.enabled},act={mads.active},avail={mads.available})"
                  f" CC.lat={cc.latActive} SDS={ss.state}(en={ss.enabled})"
                  f" cruise={cs.cruiseState.available} gear={cs.gearShifter}")

if __name__ == "__main__":
    main()
