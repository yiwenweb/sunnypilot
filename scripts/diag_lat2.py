#!/usr/bin/env python3
"""诊断横向控制 — 检查 CAN 发送和 EPS 状态"""
import cereal.messaging as messaging

sm = messaging.SubMaster(['carState', 'carControl', 'carOutput', 'sendcan', 'can'])
print("=== 检查横向控制 CAN 发送 (行驶中运行) ===")
for i in range(60):
    sm.update(1000)
    if not sm.updated['carState']:
        continue

    cs = sm['carState']
    cc = sm['carControl']

    # 从 carOutput 获取实际发送的扭矩
    co = sm['carOutput'] if sm.updated['carOutput'] else None

    print(f"\n--- tick {i} ---")
    print(f"  latActive={cc.latActive} vEgo={cs.vEgo:.1f}")
    print(f"  actuators: torque={cc.actuators.torque:.3f} angle={cc.actuators.steeringAngleDeg:.1f}")
    print(f"  steeringAngle={cs.steeringAngleDeg:.1f} steeringRate={cs.steeringRateDeg:.1f}")
    print(f"  steerTorqueDriver={cs.steeringTorque:.0f} steerTorqueEps={cs.steeringTorqueEps:.0f}")

    if co:
        print(f"  carOutput: torque={co.actuatorsOutput.torque:.3f} torqueOutputCan={co.actuatorsOutput.torqueOutputCan}")

    # 检查 sendcan 中是否有 790 消息
    if sm.updated['sendcan']:
        for msg in sm['sendcan']:
            addr = msg.address
            bus = msg.src
            if addr in (790, 813, 814, 815, 944):
                dat_hex = msg.dat.hex()
                print(f"  TX: addr={addr} bus={bus} dat={dat_hex}")

    # 检查 can 中 792 (ACC_EPS_STATE) 的 LKAS_Prepared
    if sm.updated['can']:
        for msg in sm['can']:
            if msg.address == 792 and msg.src == 0:
                dat = msg.dat
                # LKAS_Prepared is bit 0 of byte 0
                lkas_prepared = dat[0] & 0x01
                print(f"  RX 792: lkas_prepared={lkas_prepared} dat={dat.hex()}")

print("done")
