#!/usr/bin/env python3
"""
BYD Engage 状态诊断

监控 openpilot 的 engage 流程:
  - selfdriveState: enabled, active
  - carState: cruiseState, buttonEvents, steerFault
  - carControl: latActive, longActive, enabled
  - controlsState: alertText

操作步骤:
  1. 启动脚本
  2. 按 ACC 开启
  3. 挂 D 档
  4. 按 SET 按钮
  5. 观察 engage 是否成功

使用方法:
  python3 /data/openpilot/opendbc_repo/scripts/diag_engage_state.py
"""

import time
import cereal.messaging as messaging


def main():
    sm = messaging.SubMaster([
        'carState', 'carControl', 'selfdriveState',
        'carParams', 'can',
    ])

    start = time.monotonic()
    last_report = 0
    btn_events_log = []

    print("=" * 80)
    print("BYD Engage 状态诊断")
    print("=" * 80)
    print("步骤: 1.按ACC → 2.挂D档 → 3.按SET → 观察engage")
    print()

    try:
        while True:
            sm.update(100)
            now = time.monotonic() - start

            # 收集按钮事件
            if sm.valid['carState'] and sm.updated['carState']:
                cs = sm['carState']
                for evt in cs.buttonEvents:
                    btn_events_log.append((now, evt.type, evt.pressed))
                    print(f"  [BTN {now:.1f}s] type={evt.type} pressed={evt.pressed}")

            if now - last_report < 1.0:
                continue
            last_report = now

            print(f"\n[{now:.0f}s]", end="")

            # carState
            if sm.valid['carState']:
                cs = sm['carState']
                print(f" ACC={'ON' if cs.cruiseState.available else 'OFF'}"
                      f" enabled={cs.cruiseState.enabled}"
                      f" speed={cs.cruiseState.speed:.1f}"
                      f" standstill={cs.standstill}"
                      f" gear={cs.gearShifter}"
                      f" brake={cs.brakePressed}"
                      f" gas={cs.gasPressed}")
                print(f"  steerAngle={cs.steeringAngleDeg:.1f}"
                      f" steerTorque={cs.steeringTorque:.0f}"
                      f" steerPressed={cs.steeringPressed}"
                      f" steerFaultT={cs.steerFaultTemporary}"
                      f" steerFaultP={cs.steerFaultPermanent}"
                      f" buttonEnable={cs.buttonEnable}")
                print(f"  vEgo={cs.vEgo:.2f} door={cs.doorOpen} belt={cs.seatbeltUnlatched}"
                      f" parkBrake={cs.parkingBrake}")

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
        for t, typ, pressed in btn_events_log:
            print(f"  [{t:.1f}s] type={typ} pressed={pressed}")
        print("\n诊断结束")


if __name__ == "__main__":
    main()
