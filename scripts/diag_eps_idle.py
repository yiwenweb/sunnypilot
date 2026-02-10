#!/usr/bin/env python3
"""检查 EPS 空闲状态 — 不按ACC，不激活任何控制，只读 792"""
import cereal.messaging as messaging

sm = messaging.SubMaster(['can', 'carState'])
print("=== 检查 EPS 空闲状态 (不要按ACC，不要操作) ===")
print("=== 观察 TorqueFail 和 SteerWarn 的默认值 ===")
cnt = 0
for i in range(300):
    sm.update(500)
    if sm.updated['can']:
        for msg in sm['can']:
            if msg.address == 792 and msg.src == 0:
                d = bytes(msg.dat)
                prepared = d[0] & 1
                cruise_act = (d[0] >> 1) & 1
                torque_fail = (d[0] >> 2) & 1
                steer_warn = (d[0] >> 4) & 1
                main_torque = (d[1] | ((d[2] & 0xF) << 8))
                if main_torque > 2047:
                    main_torque -= 4096
                drv_torque = (d[3] | ((d[4] & 0xF) << 8))
                if drv_torque > 2047:
                    drv_torque -= 4096
                cnt += 1
                if cnt % 10 == 1:  # 每10条打印一次
                    cs_vego = sm['carState'].vEgo if sm.updated['carState'] else -1
                    print(f"  792[{cnt:3d}]: Prep={prepared} CruAct={cruise_act} TFail={torque_fail} SWarn={steer_warn} MainT={main_torque:4d} DrvT={drv_torque:4d} vEgo={cs_vego:.1f} raw={d.hex()}")

            # 也看看 Bus 2 上原厂 MPC 的 790
            if msg.address == 790 and msg.src == 2:
                d = bytes(msg.dat)
                lkas_out = (d[2] | ((d[3] & 0x07) << 8))
                if lkas_out > 1023:
                    lkas_out -= 2048
                lkas_req = (d[3] >> 3) & 1
                lkas_act = (d[3] >> 4) & 1
                cnt += 1
                if cnt % 10 == 1:
                    print(f"  790[bus2]: Output={lkas_out:4d} ReqPrep={lkas_req} Active={lkas_act} raw={d.hex()}")

print("done")
