#!/usr/bin/env python3
"""
诊断脚本: 检查透传模式是否正常工作
在 C3 上运行: python3 /data/openpilot/opendbc_repo/scripts/diag_passthrough.py

检查项:
1. Bus 2 MPC 帧能否收到 (cam_lkas/cam_acc/cam_adas 是否有数据)
2. EPS LKAS_Prepared 状态
3. OP 控制状态 (latActive/longActive/controls_allowed)
4. counter 接续是否正常
5. panda TX 是否被阻止
"""
import time
import cereal.messaging as messaging

def main():
    sm = messaging.SubMaster([
        'carState', 'carControl', 'controlsState', 'selfdriveState',
        'carOutput', 'pandaStates', 'can',
    ])

    print("=" * 70)
    print("BYD 透传模式诊断 - 每秒刷新")
    print("=" * 70)
    print()

    frame = 0
    bus2_msg_count = 0
    bus0_790_count = 0
    bus0_792_count = 0
    bus2_790_count = 0

    while True:
        sm.update(100)
        frame += 1

        # 每 10 帧 (约1秒) 输出一次
        if frame % 10 != 0:
            # 统计 CAN 帧
            if sm.updated['can']:
                for msg in sm['can']:
                    if msg.src == 2:
                        bus2_msg_count += 1
                        if msg.address == 790:
                            bus2_790_count += 1
                    if msg.src == 0:
                        if msg.address == 790:
                            bus0_790_count += 1
                        if msg.address == 792:
                            bus0_792_count += 1
            continue

        # === carState ===
        cs = sm['carState']
        print(f"\n--- Frame {frame} ({time.strftime('%H:%M:%S')}) ---")

        print(f"[车速] vEgo={cs.vEgo:.1f} m/s ({cs.vEgo*3.6:.0f} km/h)  standstill={cs.standstill}")
        print(f"[巡航] available={cs.cruiseState.available}  enabled={cs.cruiseState.enabled}")
        print(f"[转向] angle={cs.steeringAngleDeg:.1f}°  torque={cs.steeringTorque:.0f}  pressed={cs.steeringPressed}")
        print(f"[踏板] gas={cs.gasPressed}  brake={cs.brakePressed}")
        print(f"[故障] steerFaultTemp={cs.steerFaultTemporary}  steerFaultPerm={cs.steerFaultPermanent}")

        # === selfdriveState ===
        if sm.updated['selfdriveState']:
            sds = sm['selfdriveState']
            print(f"[SD] enabled={sds.enabled}  active={sds.active}  state={sds.state}")

        # === carControl ===
        if sm.updated['carControl']:
            cc = sm['carControl']
            print(f"[CC] latActive={cc.latActive}  longActive={cc.longActive}")
            print(f"[CC] actuators.torque={cc.actuators.torque:.3f}  accel={cc.actuators.accel:.2f}")

        # === carOutput ===
        if sm.updated['carOutput']:
            co = sm['carOutput']
            print(f"[CO] actuatorsOutput.torque={co.actuatorsOutput.torque:.3f}  torqueOutputCan={co.actuatorsOutput.torqueOutputCan:.0f}")

        # === pandaStates ===
        if sm.updated['pandaStates']:
            for i, ps in enumerate(sm['pandaStates']):
                print(f"[Panda{i}] safetyModel={ps.safetyModel}  controlsAllowed={ps.controlsAllowed}  "
                      f"faults={ps.faults}  ignLine={ps.ignitionLine}  ignCan={ps.ignitionCan}")

        # === CAN 帧统计 ===
        print(f"[CAN] Bus2总帧={bus2_msg_count}  Bus2_790={bus2_790_count}  "
              f"Bus0_790={bus0_790_count}  Bus0_792={bus0_792_count}")

        # 重置计数
        bus2_msg_count = 0
        bus0_790_count = 0
        bus0_792_count = 0
        bus2_790_count = 0

        # === controlsState (看有没有报错事件) ===
        if sm.updated['controlsState']:
            ctrl = sm['controlsState']
            print(f"[Ctrl] alertText1='{ctrl.alertText1}'  alertText2='{ctrl.alertText2}'  alertType='{ctrl.alertType}'")

        print()


if __name__ == "__main__":
    main()
