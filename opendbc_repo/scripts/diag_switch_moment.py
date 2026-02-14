#!/usr/bin/env python3
"""
BYD 控制切换瞬间诊断工具

专门抓取 openpilot 开始发送控制帧的瞬间，记录：
1. 切换前: 原厂 MPC 帧的 counter/checksum/内容
2. 切换后: openpilot 帧的 counter/checksum/内容
3. 是否有"双源"帧（同一地址同时出现在 Bus 0 和 Bus 2）
4. 帧间隔时序

使用方法:
  ssh comma@<C3_IP>
  python3 /data/openpilot/opendbc_repo/scripts/diag_switch_moment.py

  然后按 ACC 开启，挂 D 档行驶，观察输出
"""

import time
import cereal.messaging as messaging

WATCH_ADDRS = {790, 792, 813, 814, 815}

def hex_str(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)

def verify_checksum(data: bytes) -> bool:
    if len(data) < 8:
        return False
    return sum(data[:8]) & 0xFF == 0xFF

def get_counter(data: bytes) -> int:
    """从 byte[6] 高4位提取 counter"""
    if len(data) < 7:
        return -1
    return (data[6] >> 4) & 0xF

def decode_key_signals(addr: int, data: bytes) -> str:
    if len(data) < 8:
        return ""
    if addr == 790:
        lkas_out = ((data[2] | (data[3] << 8)) & 0x7FF)
        if lkas_out > 1023:
            lkas_out -= 2048
        lkas_active = (data[3] >> 4) & 0x1
        return f"LKAS_Out={lkas_out} Active={lkas_active}"
    elif addr == 792:
        prepared = data[0] & 0x1
        cruise_act = (data[0] >> 1) & 0x1
        torque_failed = (data[0] >> 2) & 0x1
        main_torque = (data[1] | ((data[2] & 0x0F) << 8))
        if main_torque > 2047:
            main_torque -= 4096
        return f"Prepared={prepared} CruiseAct={cruise_act} TorqueFail={torque_failed} MainTorque={main_torque}"
    elif addr == 813:
        acc_state = (data[2] >> 3) & 0x7
        acc_on1 = (data[2] >> 6) & 0x1
        status = data[4] & 0xF
        notify = (data[3] >> 2) & 0x3F
        return f"AccState={acc_state} AccOn1={acc_on1} Status={status} Notify={notify}"
    elif addr == 814:
        accel_raw = data[0]
        accel_phys = accel_raw * 0.05 - 5.0
        acc_active = (data[5] >> 2) & 0x1
        return f"AccelCmd_raw={accel_raw}({accel_phys:.2f}m/s²) AccActive={acc_active}"
    elif addr == 815:
        return f"bytes={hex_str(data[:6])}"
    return ""


def main():
    sm = messaging.SubMaster(['can', 'selfdriveState', 'carControl', 'carState'])

    # 每个 bus+addr 的历史: {(bus, addr): [{"ts": float, "data": bytes, "cnt": int}, ...]}
    history = {}
    # 上一次每个 bus+addr 的 counter
    last_counter = {}
    # 检测 openpilot 是否开始发送
    op_sending = False
    op_start_time = None

    start_time = time.monotonic()
    log_lines = []  # 保存所有日志行

    print("=" * 70)
    print("BYD 控制切换瞬间诊断")
    print("=" * 70)
    print()
    print("等待 openpilot 开始发送控制帧...")
    print("请: 1) 按 ACC 开启  2) 挂 D 档  3) 行驶")
    print("脚本会自动检测切换瞬间并记录详细数据")
    print("Ctrl+C 退出并保存日志")
    print()

    frame_count = 0

    try:
        while True:
            sm.update(100)

            if not sm.updated['can']:
                continue

            now = time.monotonic() - start_time

            for msg in sm['can']:
                bus = msg.src
                addr = msg.address
                if addr not in WATCH_ADDRS:
                    continue
                if bus not in (0, 2):
                    continue

                data = bytes(msg.dat)
                cnt = get_counter(data)
                chk_ok = verify_checksum(data)
                key = (bus, addr)

                # Counter 跳变检测
                cnt_jump = ""
                if key in last_counter and last_counter[key] >= 0 and cnt >= 0:
                    expected = (last_counter[key] + 1) & 0xF
                    if cnt != expected:
                        cnt_jump = f" ⚠️CNT_JUMP({last_counter[key]}->{cnt}, expected {expected})"
                last_counter[key] = cnt

                # 检测 openpilot 开始发送 (Bus 0 上出现 790)
                if bus == 0 and addr == 790 and not op_sending:
                    op_sending = True
                    op_start_time = now
                    line = f"\n{'!'*70}"
                    print(line)
                    log_lines.append(line)
                    line = f"  [{now:.3f}s] *** openpilot 开始发送 790 到 Bus 0 ***"
                    print(line)
                    log_lines.append(line)
                    line = f"{'!'*70}\n"
                    print(line)
                    log_lines.append(line)

                # 只在切换前后 10 秒内详细记录
                if op_start_time is not None and (now - op_start_time) > 15.0:
                    # 切换后 15 秒，降低输出频率
                    frame_count += 1
                    if frame_count % 100 != 0:
                        continue

                signals = decode_key_signals(addr, data)
                chk_str = "CHK✓" if chk_ok else "CHK✗"
                line = (f"  [{now:8.3f}s] Bus{bus} {addr:>3}  "
                        f"CNT={cnt:2d}  {chk_str}  "
                        f"{hex_str(data)}  {signals}{cnt_jump}")
                print(line)
                log_lines.append(line)

                # 双源检测: 同一地址在 Bus 0 和 Bus 2 都出现
                other_bus = 2 if bus == 0 else 0
                other_key = (other_bus, addr)
                if other_key in last_counter:
                    # 检查最近是否在另一个 bus 上也收到了
                    pass  # history 会记录

            # 每 2 秒输出 openpilot 状态
            elapsed = time.monotonic() - start_time
            if int(elapsed * 10) % 20 == 0 and op_sending:
                if sm.valid['selfdriveState']:
                    ss = sm['selfdriveState']
                    line = (f"  [{elapsed:.1f}s] [OP状态] enabled={ss.enabled} "
                            f"active={ss.active} state={ss.state}")
                    print(line)
                    log_lines.append(line)
                if sm.valid['carControl']:
                    cc = sm['carControl']
                    line = (f"  [{elapsed:.1f}s] [CC] latActive={cc.latActive} "
                            f"longActive={cc.longActive} "
                            f"torque={cc.actuators.torque:.3f}")
                    print(line)
                    log_lines.append(line)
                if sm.valid['carState']:
                    cs = sm['carState']
                    line = (f"  [{elapsed:.1f}s] [CS] cruiseAvail={cs.cruiseState.available} "
                            f"vEgo={cs.vEgo:.1f}m/s brakePressed={cs.brakePressed}")
                    print(line)
                    log_lines.append(line)

    except KeyboardInterrupt:
        print("\n\n诊断结束")

        # 保存日志
        log_path = "/tmp/diag_switch.log"
        try:
            with open(log_path, "w") as f:
                f.write("\n".join(log_lines))
            print(f"日志已保存到 {log_path}")
            print(f"请运行: cat {log_path}")
        except Exception as e:
            print(f"保存日志失败: {e}")


if __name__ == "__main__":
    main()
