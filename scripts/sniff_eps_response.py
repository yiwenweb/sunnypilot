#!/usr/bin/env python3
"""
诊断: 同时监听 790 (OP发送) 和 792 (EPS回复) 来确认 EPS 是否响应
用法: python3 /data/openpilot/scripts/sniff_eps_response.py

重点关注:
- 790 bus=0x80(TX): OP发送的扭矩命令
- 792 bus=0: EPS 真实回复 (MainTorque 是否非零)
- 792 bus=0x80(TX): OP发送的 fake 792 到 Bus 2
"""
import time
from cereal import messaging

sm = messaging.SubMaster(['can'])

print("同时监听 790 和 792...")
print("按 Ctrl+C 退出\n")

last_790_torque = 0
last_792_main = 0
last_792_prepared = 0

for i in range(500):  # ~50 seconds
    sm.update(200)
    
    if not sm.updated['can']:
        continue
    
    for msg in sm['can']:
        # 790 from OP (TX flag = bus 128)
        if msg.address == 0x316 and msg.src == 128:
            dat = bytes(msg.dat)
            lkas_out = (dat[2] | (dat[3] << 8)) & 0x7FF
            if lkas_out > 1023:
                lkas_out -= 2048
            lkas_active = (dat[3] >> 4) & 1
            mpc_state = (dat[1] >> 3) & 0xF
            lkas_state = (dat[4] >> 4) & 0xF
            req_prepare = (dat[3] >> 3) & 1
            counter = (dat[6] >> 4) & 0xF
            
            if lkas_out != last_790_torque or abs(lkas_out) > 0:
                print(f"  TX 790: Out={lkas_out:4d} Act={lkas_active} "
                      f"ReqP={req_prepare} MPC_St={mpc_state} "
                      f"LKAS_St={lkas_state} cnt={counter}")
                last_790_torque = lkas_out
        
        # 792 from EPS (real, on Bus 0)
        if msg.address == 0x318 and msg.src == 0:
            dat = bytes(msg.dat)
            prepared = dat[0] & 1
            cruise_act = (dat[0] >> 1) & 1
            torque_failed = (dat[0] >> 2) & 1
            steer_warning = (dat[0] >> 4) & 1
            main_torque = (dat[1] | (dat[2] << 8)) & 0xFFF
            if main_torque > 2047:
                main_torque -= 4096
            driver_torque = ((dat[3] | (dat[4] << 8)) & 0xFFF)
            if driver_torque > 2047:
                driver_torque -= 4096
            counter = (dat[6] >> 4) & 0xF
            
            if main_torque != last_792_main or prepared != last_792_prepared:
                print(f"  RX 792: MainTrq={main_torque:4d} Prep={prepared} "
                      f"CruAct={cruise_act} TrqFail={torque_failed} "
                      f"StWarn={steer_warning} DrvTrq={driver_torque:4d} cnt={counter}")
                last_792_main = main_torque
                last_792_prepared = prepared

print("\n完成")
