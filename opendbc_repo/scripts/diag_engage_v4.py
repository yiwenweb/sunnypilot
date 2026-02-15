#!/usr/bin/env python3
"""
BYD Engage 链路诊断 v4 — 精确追踪 buttonEnable 帧的所有事件

核心问题: buttonEnable=TRUE 触发但 SDS.enabled 不变
本脚本在 buttonEnable=TRUE 的精确帧上显示所有 onroadEvents，
帮助定位是哪个 NO_ENTRY 事件阻止了 engage。

用法: python3 /data/openpilot/opendbc_repo/scripts/diag_engage_v4.py
"""

import time
import cereal.messaging as messaging
from openpilot.common.params import Params


def main():
    params = Params()

    print("=" * 78)
    print("BYD Engage 链路诊断 v4 — buttonEnable 帧事件追踪")
    print("=" * 78)

    # MADS 参数
    mads = params.get_bool("Mads")
    mads_main = params.get_bool("MadsMainCruiseAllowed")
    mads_uem = params.get_bool("MadsUnifiedEngagementMode")
    op_enabled = params.get_bool("OpenpilotEnabledToggle")
    print(f"MADS: Mads={mads} MainCruise={mads_main} UEM={mads_uem} OpEnabled={op_enabled}")
    print("-" * 78)

    sm = messaging.SubMaster([
        'carState', 'carControl', 'selfdriveState', 'pandaStates',
        'onroadEvents', 'selfdriveStateSP', 'onroadEventsSP',
    ])

    start = time.monotonic()
    last_report = 0
    enabled_prev = None
    ca_prev = None

    try:
        while True:
            sm.update(10)  # 10ms = 100Hz polling for precision
            now = time.monotonic() - start

            # === 每帧检查 buttonEnable ===
            if sm.valid['carState'] and sm.updated['carState']:
                cs = sm['carState']

                # 按钮事件
                for evt in cs.buttonEvents:
                    print(f"  [{now:.3f}s] BTN: {evt.type} pressed={evt.pressed}")

                # buttonEnable 精确帧
                if cs.buttonEnable:
                    print(f"\n  >>> [{now:.3f}s] buttonEnable=TRUE <<<")

                    # 显示此帧的所有 onroadEvents
                    if sm.valid['onroadEvents']:
                        events = sm['onroadEvents']
                        if len(events) > 0:
                            print(f"      onroadEvents ({len(events)}):")
                            for e in events:
                                print(f"        - {e.name}")
                        else:
                            print(f"      onroadEvents: (empty)")

                    # 显示 SP events
                    if sm.valid['onroadEventsSP']:
                        events_sp = sm['onroadEventsSP'].events
                        if len(events_sp) > 0:
                            print(f"      onroadEventsSP ({len(events_sp)}):")
                            for e in events_sp:
                                print(f"        - {e.name}")

                    # 显示关键状态
                    print(f"      CS: gear={cs.gearShifter} brake={cs.brakePressed}"
                          f" standstill={cs.standstill} vEgo={cs.vEgo:.2f}")
                    print(f"      CS: steerPressed={cs.steeringPressed}"
                          f" steerFaultT={cs.steerFaultTemporary}"
                          f" steerFaultP={cs.steerFaultPermanent}")
                    print(f"      CS: doorOpen={cs.doorOpen} seatbelt={cs.seatbeltUnlatched}"
                          f" parkBrake={cs.parkingBrake} espDisabled={cs.espDisabled}")
                    print(f"      CS: cruiseAvail={cs.cruiseState.available}"
                          f" cruiseEnabled={cs.cruiseState.enabled}"
                          f" vCruise={cs.vCruise:.1f}")

                    # panda 状态
                    if sm.valid['pandaStates']:
                        for ps in sm['pandaStates']:
                            if str(ps.safetyModel) != 'silent':
                                print(f"      PANDA: controlsAllowed={ps.controlsAllowed}"
                                      f" rxInvalid={ps.safetyRxChecksInvalid}"
                                      f" safety={ps.safetyModel}"
                                      f" altExp={ps.alternativeExperience}")

                    # selfdriveState
                    if sm.valid['selfdriveState']:
                        sds = sm['selfdriveState']
                        print(f"      SDS: enabled={sds.enabled} state={sds.state}"
                              f" engageable={sds.engageable}")

                    # MADS state
                    if sm.valid['selfdriveStateSP']:
                        mads_sp = sm['selfdriveStateSP'].mads
                        print(f"      MADS: state={mads_sp.state} enabled={mads_sp.enabled}"
                              f" active={mads_sp.active}")

                    print()

            # === controlsAllowed 变化 ===
            if sm.valid['pandaStates'] and sm.updated['pandaStates']:
                ca = any(ps.controlsAllowed for ps in sm['pandaStates']
                         if str(ps.safetyModel) != 'silent')
                if ca != ca_prev:
                    print(f"  [{now:.3f}s] controlsAllowed: {ca_prev} → {ca}")
                    ca_prev = ca

            # === enabled 变化 ===
            if sm.valid['selfdriveState'] and sm.updated['selfdriveState']:
                sds = sm['selfdriveState']
                if sds.enabled != enabled_prev:
                    print(f"  [{now:.3f}s] SDS.enabled: {enabled_prev} → {sds.enabled}"
                          f"  state={sds.state}")
                    if sds.alertText1:
                        print(f"             alert: {sds.alertText1}")
                    enabled_prev = sds.enabled

            # === 每5秒状态报告 ===
            if now - last_report >= 5.0:
                last_report = now
                acc = "?"
                gear = "?"
                vego = 0
                if sm.valid['carState']:
                    cs = sm['carState']
                    acc = "ON" if cs.cruiseState.available else "OFF"
                    gear = str(cs.gearShifter)
                    vego = cs.vEgo

                ca_str = ca_prev if ca_prev is not None else "?"
                en_str = enabled_prev if enabled_prev is not None else "?"

                rx_invalid = "?"
                if sm.valid['pandaStates']:
                    for ps in sm['pandaStates']:
                        if str(ps.safetyModel) != 'silent':
                            rx_invalid = ps.safetyRxChecksInvalid

                print(f"\n--- [{now:.0f}s] ACC={acc} gear={gear} vEgo={vego:.2f}"
                      f" CA={ca_str} enabled={en_str} rxInvalid={rx_invalid} ---")

                # 显示当前所有事件
                if sm.valid['onroadEvents']:
                    events = sm['onroadEvents']
                    if len(events) > 0:
                        evt_names = [str(e.name) for e in events]
                        print(f"    EVENTS: {', '.join(evt_names)}")
                print()

    except KeyboardInterrupt:
        print("\n诊断结束")


if __name__ == "__main__":
    main()
