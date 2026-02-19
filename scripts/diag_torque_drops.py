#!/usr/bin/env python3
"""
诊断: 监控转弯时扭矩是否中断
=============================
用法: python3 /data/openpilot/scripts/diag_torque_drops.py

监控内容:
1. OP 发送的 790 扭矩命令 (TX bus=128)
2. EPS 回复的 792 实际扭矩 (RX bus=0)
3. 检测扭矩突然归零的情况
4. 检测 790 发送间隔是否超过 100ms (fwd_hook 超时)
5. 检测 panda safety_tx_blocked 计数
"""
import time
from panda import Panda
from cereal import messaging

sm = messaging.SubMaster(['can', 'pandaStates'])

logfile = '/tmp/torque_diag.log'
f = open(logfile, 'w')

last_790_time = 0
last_790_torque = 0
last_792_main = 0
last_792_time = 0
drop_count = 0
gap_count = 0

f.write(f"# 扭矩中断诊断 {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
f.write("# 格式: [时间] 事件 详情\n\n")

print("扭矩中断诊断开始...")
print("按 ACC 激活横向控制，然后转弯测试")
print("按 Ctrl+C 停止\n")

t0 = time.monotonic()
frame = 0
safety_tx_blocked_last = 0

try:
    while True:
        sm.update(100)
        t = time.monotonic() - t0

        # Check pandaStates for safety_tx_blocked
        if sm.updated['pandaStates'] and len(sm['pandaStates']) > 0:
            ps = sm['pandaStates'][0]
            stb = ps.safetyTxBlocked
            if stb != safety_tx_blocked_last:
                delta = stb - safety_tx_blocked_last
                line = f"[{t:8.3f}] SAFETY_TX_BLOCKED: {safety_tx_blocked_last} -> {stb} (delta={delta})"
                f.write(line + "\n")
                print(line)
                safety_tx_blocked_last = stb

        if not sm.updated['can']:
            continue

        for msg in sm['can']:
            # 790 from OP (TX to Bus 0, src=128)
            if msg.address == 0x316 and msg.src == 128:
                dat = bytes(msg.dat)
                lkas_out = (dat[2] | (dat[3] << 8)) & 0x7FF
                if lkas_out > 1023:
                    lkas_out -= 2048
                lkas_active = (dat[3] >> 4) & 1
                counter = (dat[6] >> 4) & 0xF

                # Check 790 send interval
                if last_790_time > 0:
                    gap_ms = (t - last_790_time) * 1000
                    if gap_ms > 50:  # Should be ~20ms at 50Hz
                        gap_count += 1
                        line = f"[{t:8.3f}] 790_GAP: {gap_ms:.1f}ms (>50ms!) cnt={counter} gaps_total={gap_count}"
                        f.write(line + "\n")
                        if gap_ms > 80:
                            print(line)

                # Check torque drop
                if abs(last_790_torque) > 20 and lkas_out == 0 and lkas_active == 0:
                    drop_count += 1
                    line = f"[{t:8.3f}] 790_DROP: torque {last_790_torque} -> 0, active=0! drops_total={drop_count}"
                    f.write(line + "\n")
                    print(line)
                elif abs(last_790_torque) > 20 and abs(lkas_out) < 3 and lkas_active == 1:
                    drop_count += 1
                    line = f"[{t:8.3f}] 790_NEAR_ZERO: torque {last_790_torque} -> {lkas_out}, active=1 drops_total={drop_count}"
                    f.write(line + "\n")
                    print(line)

                last_790_torque = lkas_out
                last_790_time = t

                # Log every 10th frame when active
                if lkas_active and frame % 10 == 0:
                    f.write(f"[{t:8.3f}] 790_TX: Out={lkas_out:4d} Act={lkas_active} cnt={counter}\n")

            # 792 from EPS (real, Bus 0)
            if msg.address == 0x318 and msg.src == 0:
                dat = bytes(msg.dat)
                main_torque = (dat[1] | (dat[2] << 8)) & 0xFFF
                if main_torque > 2047:
                    main_torque -= 4096
                prepared = dat[0] & 1
                cruise_act = (dat[0] >> 1) & 1
                driver_torque = ((dat[3] | (dat[4] << 8)) & 0xFFF)
                if driver_torque > 2047:
                    driver_torque -= 4096

                # Check EPS torque drop
                if abs(last_792_main) > 10 and main_torque == 0:
                    line = f"[{t:8.3f}] 792_EPS_DROP: MainTrq {last_792_main} -> 0! Prep={prepared} CruAct={cruise_act} DrvTrq={driver_torque}"
                    f.write(line + "\n")
                    print(line)

                # Log EPS response when non-zero
                if main_torque != 0 and frame % 10 == 0:
                    f.write(f"[{t:8.3f}] 792_RX: MainTrq={main_torque:4d} Prep={prepared} CruAct={cruise_act} DrvTrq={driver_torque:4d}\n")

                # Always log when main torque changes significantly
                if abs(main_torque - last_792_main) > 20:
                    f.write(f"[{t:8.3f}] 792_CHANGE: MainTrq {last_792_main} -> {main_torque} DrvTrq={driver_torque}\n")

                last_792_main = main_torque
                last_792_time = t

            # 790 from MPC (Bus 2 -> should be blocked by fwd_hook)
            if msg.address == 0x316 and msg.src == 2:
                dat = bytes(msg.dat)
                lkas_out_mpc = (dat[2] | (dat[3] << 8)) & 0x7FF
                if lkas_out_mpc > 1023:
                    lkas_out_mpc -= 2048
                counter_mpc = (dat[6] >> 4) & 0xF
                # This should NOT appear on Bus 0 when OP is steering
                # But we see it on Bus 2 (MPC side) - that's normal
                if frame % 50 == 0:
                    f.write(f"[{t:8.3f}] 790_MPC: Out={lkas_out_mpc:4d} cnt={counter_mpc} (Bus2 normal)\n")

        frame += 1

except KeyboardInterrupt:
    pass

f.write(f"\n# 结束: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
f.write(f"# 扭矩中断次数: {drop_count}\n")
f.write(f"# 790发送间隔>50ms次数: {gap_count}\n")
f.write(f"# safety_tx_blocked最终值: {safety_tx_blocked_last}\n")
f.close()

print(f"\n诊断完成!")
print(f"扭矩中断次数: {drop_count}")
print(f"790发送间隔>50ms次数: {gap_count}")
print(f"数据保存: {logfile}")
print(f"查看: cat {logfile}")
print(f"只看中断: grep -E 'DROP|GAP|BLOCKED' {logfile}")
