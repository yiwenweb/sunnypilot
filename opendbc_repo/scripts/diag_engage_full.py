#!/usr/bin/env python3
"""
BYD 完整 Engage 链路诊断

同时监控:
1. panda 安全层: controlsAllowed (来自 pandaStates)
2. carState: buttonEnable, cruiseState
3. selfdriveState: enabled, state
4. MADS 参数

用法: python3 /data/openpilot/opendbc_repo/scripts/diag_engage_full.py
"""

import time
import cereal.messaging as messaging
from openpilot.common.params import Params

def main():
    params = Params()

    print("=" * 78)
    print("BYD 完整 Engage 链路诊断")
    print("=" * 78)

    # 读取 MADS 参数
    mads = params.get_bool("Mads")
    mads_main = params.get_bool("MadsMainCruiseAllowed")
    mads_uem = params.get_bool("MadsUnifiedEngagementMode")
    op_enabled = params.get_bool("OpenpilotEnabledToggle")
    print(f"MADS参数: Mads={mads} MainCruise={mads_main} UEM={mads_uem} OpEnabled={op_enabled}")

    if not mads_uem:
        print("*** 警告: MadsUnifiedEngagementMode=False → buttonEnable 事件会被 MADS 移除! ***")

    print("-" * 78)

    sm = messaging.SubMaster([
        'carState', 'carControl', 'selfdriveState', 'pandaStates', 'onroadEvents',
    ])

    start = time.monotonic()
    last_report = 0
    btn_log = []

    try:
        while True:
            sm.update(100)
            now = time.monotonic() - start

            # 按钮事件 (每次都检查)
            if sm.valid['carState'] and sm.updated['carState']:
                cs = sm['carState']
                for evt in cs.buttonEvents:
                    btn_log.append((now, evt.type, evt.pressed))
                    print(f"  [BTN {now:.1f}s] type={evt.type} pressed={evt.pressed}")

                # buttonEnable 是瞬时值，必须每帧检查
                if cs.buttonEnable:
                    print(f"  >>> [BTN {now:.1f}s] buttonEnable=TRUE <<<")

            # 每秒报告
            if now - last_report < 1.0:
                continue
            last_report = now

            # panda 状态
            panda_ca = "?"
            panda_safety = "?"
            panda_alt = 0
            if sm.valid['pandaStates']:
                for ps in sm['pandaStates']:
                    panda_ca = ps.controlsAllowed
                    panda_safety = ps.safetyModel
                    panda_alt = ps.alternativeExperience

            # carState
            if sm.valid['carState']:
                cs = sm['carState']
                acc = "ON" if cs.cruiseState.available else "OFF"
                print(f"\n[{now:.0f}s] ACC={acc} gear={cs.gearShifter} brake={cs.brakePressed}"
                      f" standstill={cs.standstill} vEgo={cs.vEgo:.2f}")
                print(f"  PANDA: controlsAllowed={panda_ca} safety={panda_safety}"
                      f" altExp={panda_alt} MADS={bool(panda_alt & 1024)}")
                print(f"  CS: buttonEnable={cs.buttonEnable}"
                      f" cruiseEnabled={cs.cruiseState.enabled}")

            # carControl
            if sm.valid['carControl']:
                cc = sm['carControl']
                print(f"  CC: latActive={cc.latActive} longActive={cc.longActive}"
                      f" enabled={cc.enabled}")

            # selfdriveState
            if sm.valid['selfdriveState']:
                sds = sm['selfdriveState']
                print(f"  SDS: enabled={sds.enabled} active={sds.active}"
                      f" state={sds.state}")
                if sds.alertText1:
                    print(f"  ALERT: {sds.alertText1}")
                    if sds.alertText2:
                        print(f"         {sds.alertText2}")

    except KeyboardInterrupt:
        print("\n\n=== 按钮事件历史 ===")
        for t, typ, pressed in btn_log:
            print(f"  [{t:.1f}s] type={typ} pressed={pressed}")
        print("\n诊断结束")


if __name__ == "__main__":
    main()
