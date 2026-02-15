#!/usr/bin/env python3
"""
BYD Panda controlsAllowed 诊断 — 精确追踪 CA 为什么始终为 False

直接读取 CAN 总线上的 PCM_BUTTONS (944) 和 DRIVE_STATE (578)，
对比 panda 报告的 controlsAllowed 状态。

用法: python3 /data/openpilot/opendbc_repo/scripts/diag_panda_ca.py
"""

import time
import cereal.messaging as messaging


def main():
    print("=" * 78)
    print("BYD Panda controlsAllowed 诊断")
    print("=" * 78)

    sm = messaging.SubMaster(['can', 'pandaStates', 'carState', 'selfdriveState'])

    start = time.monotonic()
    last_report = 0

    # 追踪状态
    last_ca = None
    last_acc_on = None
    last_brake = None
    btn_944_count = 0
    ds_578_count = 0
    last_944_raw = None
    last_578_raw = None
    mads_lat = None

    try:
        while True:
            sm.update(10)
            now = time.monotonic() - start

            # 解析 CAN 消息
            if sm.updated['can']:
                for msg in sm['can']:
                    addr = msg.address
                    bus = msg.src
                    dat = bytes(msg.dat)

                    if addr == 944 and bus == 0:
                        btn_944_count += 1
                        last_944_raw = dat.hex()
                        # BTN_TOGGLE_ACC_OnOff: bit 8 (byte1, bit0)
                        acc_on = (dat[1] >> 0) & 1
                        if acc_on != last_acc_on:
                            print(f"  [{now:.3f}s] 944: ACC_OnOff={acc_on} (was {last_acc_on}) raw={dat.hex()}")
                            last_acc_on = acc_on

                    if addr == 578 and bus == 0:
                        ds_578_count += 1
                        last_578_raw = dat.hex()
                        # BrakePressed: bit 37 = byte4, bit5
                        brake = (dat[4] >> 5) & 1
                        # Gear: bits 40-42 = byte5, bits 0-2
                        gear = dat[5] & 0x7
                        if brake != last_brake:
                            print(f"  [{now:.3f}s] 578: BrakePressed={brake} (was {last_brake})"
                                  f" gear={gear} raw={dat.hex()}")
                            last_brake = brake

            # 追踪 panda CA 变化
            if sm.updated['pandaStates']:
                for ps in sm['pandaStates']:
                    if str(ps.safetyModel) == 'silent':
                        continue
                    ca = ps.controlsAllowed
                    rx_inv = ps.safetyRxChecksInvalid
                    if ca != last_ca:
                        print(f"  [{now:.3f}s] PANDA: CA={ca} (was {last_ca})"
                              f" rxInvalid={rx_inv}")
                        last_ca = ca

            # 每 3 秒报告
            if now - last_report < 3.0:
                continue
            last_report = now

            # 状态摘要
            ca_str = last_ca if last_ca is not None else "?"
            acc_str = last_acc_on if last_acc_on is not None else "?"
            brake_str = last_brake if last_brake is not None else "?"

            print(f"\n[{now:.0f}s] CA={ca_str} ACC_ON={acc_str} brake={brake_str}"
                  f" 944_cnt={btn_944_count} 578_cnt={ds_578_count}")

            if last_944_raw:
                print(f"  last 944: {last_944_raw}")
            if last_578_raw:
                print(f"  last 578: {last_578_raw}")

            # carState 对比
            if sm.valid['carState']:
                cs = sm['carState']
                print(f"  CS: vEgo={cs.vEgo:.2f} brake={cs.brakePressed}"
                      f" gas={cs.gasPressed} steerPressed={cs.steeringPressed}"
                      f" steerTorque={cs.steeringTorque:.0f}")
                print(f"  CS: cruiseAvail={cs.cruiseState.available}"
                      f" gear={cs.gearShifter}")

            if sm.valid['selfdriveState']:
                sds = sm['selfdriveState']
                print(f"  SDS: enabled={sds.enabled} state={sds.state}")

            print()

    except KeyboardInterrupt:
        print("\n诊断结束")


if __name__ == "__main__":
    main()
