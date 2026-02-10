#!/usr/bin/env python3
"""直接解析 790 TX 和 792 RX 的原始 CAN 数据"""
import cereal.messaging as messaging

sm = messaging.SubMaster(['sendcan', 'can'])
print("=== 解析 790/813 TX 和 792 RX (行驶中运行) ===")
for i in range(200):
    sm.update(500)

    # 解析 sendcan 中的 790 和 813
    if sm.updated['sendcan']:
        for msg in sm['sendcan']:
            if msg.address == 790 and msg.src == 0:
                d = bytes(msg.dat)
                # LKAS_Output: bits 16-26, 11-bit signed
                lkas_out_raw = (d[2] | ((d[3] & 0x07) << 8))
                if lkas_out_raw > 1023:
                    lkas_out_raw -= 2048
                # LKAS_ReqPrepare: bit 27
                lkas_req = (d[3] >> 3) & 1
                # LKAS_Active: bit 28
                lkas_act = (d[3] >> 4) & 1
                # LKAS_Config: bits 6-7
                lkas_cfg = (d[0] >> 6) & 3
                # COUNTER: bits 52-55
                cnt = (d[6] >> 4) & 0xF
                print(f"TX 790: Output={lkas_out_raw:4d} ReqPrepare={lkas_req} Active={lkas_act} Config={lkas_cfg} cnt={cnt} raw={d.hex()}")

            if msg.address == 813 and msg.src == 0:
                d = bytes(msg.dat)
                # AccState: bits 19-21
                acc_state = (d[2] >> 3) & 0x7
                # AccOn1: bit 22
                acc_on = (d[2] >> 6) & 1
                # SetSpeed: bits 0-8, scale 0.5
                set_spd = ((d[0] | ((d[1] & 1) << 8))) * 0.5
                print(f"TX 813: AccState={acc_state} AccOn={acc_on} SetSpeed={set_spd:.1f} raw={d.hex()}")

    # 解析 can 中的 792
    if sm.updated['can']:
        for msg in sm['can']:
            if msg.address == 792 and msg.src == 0:
                d = bytes(msg.dat)
                # LKAS_Prepared: bit 0
                prepared = d[0] & 1
                # CruiseActivated: bit 1
                cruise_act = (d[0] >> 1) & 1
                # TorqueFailed: bit 2
                torque_fail = (d[0] >> 2) & 1
                # SteerWarning: bit 4
                steer_warn = (d[0] >> 4) & 1
                # MainTorque: bits 8-19, 12-bit signed
                main_torque = (d[1] | ((d[2] & 0xF) << 8))
                if main_torque > 2047:
                    main_torque -= 4096
                # SteerDriverTorque: bits 24-35, 12-bit signed
                drv_torque = (d[3] | ((d[4] & 0xF) << 8))
                if drv_torque > 2047:
                    drv_torque -= 4096
                print(f"RX 792: Prepared={prepared} CruiseAct={cruise_act} TorqueFail={torque_fail} SteerWarn={steer_warn} MainTorque={main_torque} DrvTorque={drv_torque} raw={d.hex()}")

print("done")
