#!/usr/bin/env python3
"""诊断横向控制 — 重点看 TX 790 和 RX 792"""
import cereal.messaging as messaging

sm = messaging.SubMaster(['carControl', 'carOutput', 'sendcan', 'can'])
print("=== 诊断 TX 790 / RX 792 (行驶中按ACC后运行) ===")
tx_790_cnt = 0
rx_792_cnt = 0
for i in range(200):
    sm.update(500)

    # 检查 sendcan 中的 790
    if sm.updated['sendcan']:
        for msg in sm['sendcan']:
            if msg.address == 790:
                d = bytes(msg.dat)
                lkas_out = (d[2] | ((d[3] & 0x07) << 8))
                if lkas_out > 1023: lkas_out -= 2048
                req_prep = (d[3] >> 3) & 1
                lkas_act = (d[3] >> 4) & 1
                config = (d[0] >> 6) & 3
                lkas_state = (d[4] >> 4) & 0xF
                cnt = (d[6] >> 4) & 0xF
                tx_790_cnt += 1
                if tx_790_cnt % 20 == 1:
                    print(f"TX 790[{tx_790_cnt:3d}]: Out={lkas_out:5d} Prep={req_prep} Act={lkas_act} Cfg={config} St={lkas_state} cnt={cnt} bus={msg.src} raw={d.hex()}")

    # 检查 can 中的 790 (看是否被接受/拒绝)
    if sm.updated['can']:
        for msg in sm['can']:
            # 790 回声
            if msg.address == 790:
                d = bytes(msg.dat)
                bus = msg.src
                if bus == 0 and tx_790_cnt > 0:
                    pass  # 正常接受，不打印（太多）
                elif bus == 192:
                    print(f"  790 REJECTED bus=192 raw={d.hex()}")
                elif bus == 2:
                    pass  # 原厂MPC，不打印

            # 792 EPS 回复
            if msg.address == 792 and msg.src == 0:
                d = bytes(msg.dat)
                prep = d[0] & 1
                cruise_act = (d[0] >> 1) & 1
                tfail = (d[0] >> 2) & 1
                swarn = (d[0] >> 4) & 1
                mt = ((d[1] | (d[2] << 8)) & 0xFFF)
                if mt > 2047: mt -= 4096
                dt = ((d[3] | (d[4] << 8)) & 0xFFF)
                if dt > 2047: dt -= 4096
                rx_792_cnt += 1
                if rx_792_cnt % 20 == 1:
                    print(f"RX 792[{rx_792_cnt:3d}]: Prep={prep} CruAct={cruise_act} TFail={tfail} SWarn={swarn} MainT={mt:5d} DrvT={dt:5d} raw={d.hex()}")

    # carControl 状态
    if sm.updated['carControl'] and i % 20 == 0:
        cc = sm['carControl']
        co = sm['carOutput'] if sm.updated['carOutput'] else None
        t_out = co.actuatorsOutput.torqueOutputCan if co else '?'
        print(f"  [{i:3d}] latActive={cc.latActive} torque={cc.actuators.torque:.3f} outputCan={t_out}")

print(f"\nTotal: TX 790={tx_790_cnt}, RX 792={rx_792_cnt}")
print("done")
