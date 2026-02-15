#!/usr/bin/env python3
"""
精确追踪 controlsAllowed 变化

每帧检查 pandaStates.controlsAllowed，记录每次变化的时间和持续时间。
同时记录 selfdriveState.enabled 的变化。

用法: python3 /data/openpilot/opendbc_repo/scripts/diag_controls_allowed.py
"""

import time
import cereal.messaging as messaging

def main():
    print("=" * 70)
    print("controlsAllowed 精确追踪")
    print("=" * 70)

    sm = messaging.SubMaster([
        'pandaStates', 'selfdriveState', 'carState', 'onroadEvents',
    ])

    start = time.monotonic()
    ca_prev = None
    enabled_prev = None
    ca_true_start = None
    last_report = 0

    try:
        while True:
            sm.update(10)  # 10ms timeout = 100Hz polling
            now = time.monotonic() - start

            # 每帧检查 controlsAllowed 变化
            if sm.valid['pandaStates'] and sm.updated['pandaStates']:
                ca = any(ps.controlsAllowed for ps in sm['pandaStates']
                         if str(ps.safetyModel) != 'silent')
                if ca != ca_prev:
                    if ca:
                        ca_true_start = now
                        print(f"  [{now:.3f}s] controlsAllowed: False → TRUE")
                    else:
                        duration = (now - ca_true_start) if ca_true_start else 0
                        print(f"  [{now:.3f}s] controlsAllowed: TRUE → False"
                              f"  (持续 {duration*1000:.0f}ms)")
                    ca_prev = ca

            # 每帧检查 enabled 变化
            if sm.valid['selfdriveState'] and sm.updated['selfdriveState']:
                sds = sm['selfdriveState']
                enabled = sds.enabled
                if enabled != enabled_prev:
                    print(f"  [{now:.3f}s] SDS.enabled: {enabled_prev} → {enabled}"
                          f"  state={sds.state}")
                    if enabled and sds.alertText1:
                        print(f"             alert: {sds.alertText1}")
                    enabled_prev = enabled

            # 按钮事件
            if sm.valid['carState'] and sm.updated['carState']:
                cs = sm['carState']
                for evt in cs.buttonEvents:
                    print(f"  [{now:.3f}s] BTN: {evt.type} pressed={evt.pressed}")
                if cs.buttonEnable:
                    print(f"  [{now:.3f}s] >>> buttonEnable=TRUE <<<")

            # onroadEvents 变化
            if sm.valid['onroadEvents'] and sm.updated['onroadEvents']:
                events = sm['onroadEvents']
                evt_names = [str(e.name) for e in events]
                # 只显示有 controlsMismatch 的
                if 'controlsMismatch' in evt_names:
                    print(f"  [{now:.3f}s] !!! controlsMismatch detected !!!")

            # 每5秒状态报告
            if now - last_report >= 5.0:
                last_report = now
                ca_str = ca_prev if ca_prev is not None else "?"
                en_str = enabled_prev if enabled_prev is not None else "?"
                acc = "?"
                if sm.valid['carState']:
                    acc = "ON" if sm['carState'].cruiseState.available else "OFF"
                print(f"\n--- [{now:.0f}s] ACC={acc} controlsAllowed={ca_str}"
                      f" enabled={en_str} ---\n")

    except KeyboardInterrupt:
        print("\n追踪结束")


if __name__ == "__main__":
    main()
