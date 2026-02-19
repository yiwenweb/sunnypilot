#!/usr/bin/env python3
"""
嗅探脚本: 在 openpilot 运行时监听 Bus 0 上的 790 消息
用法: python3 /data/openpilot/scripts/sniff_790_live.py

通过 cereal 的 can 消息来查看 790 是否真的到达 Bus 0
以及 790 的内容 (LKAS_Output, LKAS_Active, MPC_State, LKAS_State)
"""
import time
from cereal import messaging

sm = messaging.SubMaster(['can'])

print("监听 CAN 消息中的 790 (ACC_MPC_STATE)...")
print("按 Ctrl+C 退出\n")

count = 0
for i in range(200):  # ~20 seconds
    sm.update(200)
    
    if sm.updated['can']:
        for msg in sm['can']:
            if msg.address == 0x316:  # 790
                dat = bytes(msg.dat)
                # Parse key fields from 790
                lkas_output_raw = (dat[2] | (dat[3] << 8)) & 0x7FF
                if lkas_output_raw > 1023:
                    lkas_output_raw -= 2048
                lkas_active = (dat[3] >> 4) & 1
                lkas_reqprepare = (dat[3] >> 3) & 1
                mpc_state = (dat[1] >> 3) & 0xF
                lkas_state = (dat[4] >> 4) & 0xF
                counter = (dat[6] >> 4) & 0xF
                checksum = dat[7]
                
                count += 1
                if count % 5 == 0:  # print every 5th to reduce spam
                    print(f"790 bus={msg.src} cnt={counter} "
                          f"LKAS_Out={lkas_output_raw:4d} Active={lkas_active} "
                          f"ReqPrep={lkas_reqprepare} MPC_St={mpc_state} "
                          f"LKAS_St={lkas_state} chk={checksum:02x} "
                          f"raw={dat.hex()}")

print(f"\n总共收到 {count} 条 790 消息")
