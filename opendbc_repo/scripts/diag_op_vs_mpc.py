#!/usr/bin/env python3
"""
BYD OP帧 vs MPC帧 实时对比诊断

同时显示:
  - Bus 0 上 OP 发送的帧 (790/813/814/815)
  - Bus 2 上 MPC 原厂帧 (790/813/814/815)
  - Bus 0 上 EPS 真实 792
  - Bus 2 上 OP 发送的假 792

重点观察:
  1. OP 帧的信号值是否正确
  2. 切换瞬间是否有间隙
  3. counter 是否连续

使用方法:
  python3 /data/openpilot/opendbc_repo/scripts/diag_op_vs_mpc.py
"""

import time
import cereal.messaging as messaging


def hex_str(data):
    return " ".join(f"{b:02x}" for b in data)


def chk_ok(data):
    return "CHK✓" if (sum(data) & 0xFF) == 0xFF else "CHK✗"


def decode_813_brief(dat):
    b = dat
    acc_state = (b[2] >> 3) & 0x7
    acc_on1 = (b[2] >> 6) & 0x1
    notify = (b[3] >> 1) & 0x7F
    status = (b[4] >> 0) & 0xF
    set_dist = (b[1] >> 2) & 0x7
    counter = (b[6] >> 0) & 0xF
    return f"AccSt={acc_state} On1={acc_on1} Nfy={notify} Sts={status} Dist={set_dist} C={counter}"


def decode_814_brief(dat):
    b = dat
    accel_raw = b[0]
    esp_beh = (b[5] >> 6) & 0x3
    acc_req = (b[5] >> 3) & 0x1
    acc_ctrl = (b[5] >> 4) & 0x1
    counter = (b[6] >> 0) & 0xF
    return f"Accel={accel_raw}(raw) EspB={esp_beh} ReqNS={acc_req} CtrlAct={acc_ctrl} C={counter}"


def decode_790_brief(dat):
    b = dat
    lkas_out = ((b[2] | (b[3] << 8)) & 0x7FF)
    if lkas_out > 1023:
        lkas_out -= 2048
    lkas_active = (b[3] >> 4) & 0x1
    mpc_state = (b[1] >> 3) & 0xF
    lkas_state = (b[4] >> 4) & 0xF
    counter = (b[6] >> 4) & 0xF
    return f"Out={lkas_out} Act={lkas_active} MPC={mpc_state} LKS={lkas_state} C={counter}"


def decode_792_brief(dat):
    b = dat
    torque_failed = (b[0] >> 2) & 0x1
    cruise_act = (b[0] >> 1) & 0x1
    lkas_prep = (b[0] >> 0) & 0x1
    mt_raw = (b[1] | ((b[2] & 0xF) << 8))
    main_torque = mt_raw - 4096 if mt_raw > 2047 else mt_raw
    counter = (b[6] >> 4) & 0xF
    return f"TF={torque_failed} CA={cruise_act} LP={lkas_prep} MT={main_torque} b0=0x{b[0]:02x} C={counter}"


def main():
    sm = messaging.SubMaster(['can', 'carState', 'carControl', 'selfdriveState'])

    # 最新帧: key = (addr, bus)
    latest = {}
    # counter 跟踪
    last_counter = {}

    start = time.monotonic()
    last_report = 0

    print("=" * 80)
    print("BYD OP帧 vs MPC帧 实时对比")
    print("=" * 80)
    print("Bus0=车辆主总线(ECU收到的)  Bus2=MPC原厂帧")
    print("OP激活时: Bus0 上应该是 OP 帧, Bus2 上是 MPC 原厂帧")
    print("OP未激活: Bus0 上应该是 MPC 转发帧, Bus2 上是 MPC 原厂帧")
    print("注意: openpilot 看不到 panda 硬件转发的帧!")
    print()

    try:
        while True:
            sm.update(100)
            if not sm.updated['can']:
                continue

            now = time.monotonic() - start

            for msg in sm['can']:
                bus = msg.src
                addr = msg.address
                if addr in (790, 792, 813, 814, 815):
                    latest[(addr, bus)] = bytes(msg.dat)

            if now - last_report < 1.0:
                continue
            last_report = now

            # 状态
            avail = lat = enabled = ""
            if sm.valid['carState']:
                cs = sm['carState']
                avail = f"ACC={'ON' if cs.cruiseState.available else 'OFF'}"
            if sm.valid['carControl']:
                cc = sm['carControl']
                lat = f"lat={'Y' if cc.latActive else 'N'}"
                enabled = f"long={'Y' if cc.longActive else 'N'}"

            print(f"\n[{now:.0f}s] {avail} {lat} {enabled}")

            # 790
            for bus_label, bus in [("Bus0(ECU)", 0), ("Bus2(MPC)", 2)]:
                raw = latest.get((790, bus))
                if raw:
                    print(f"  790 {bus_label}: {hex_str(raw)} {chk_ok(raw)} {decode_790_brief(raw)}")

            # 813
            for bus_label, bus in [("Bus0(ECU)", 0), ("Bus2(MPC)", 2)]:
                raw = latest.get((813, bus))
                if raw:
                    print(f"  813 {bus_label}: {hex_str(raw)} {chk_ok(raw)} {decode_813_brief(raw)}")

            # 814
            for bus_label, bus in [("Bus0(ECU)", 0), ("Bus2(MPC)", 2)]:
                raw = latest.get((814, bus))
                if raw:
                    print(f"  814 {bus_label}: {hex_str(raw)} {chk_ok(raw)} {decode_814_brief(raw)}")

            # 792
            for bus_label, bus in [("Bus0(EPS)", 0), ("Bus2(OP)", 2)]:
                raw = latest.get((792, bus))
                if raw:
                    print(f"  792 {bus_label}: {hex_str(raw)} {chk_ok(raw)} {decode_792_brief(raw)}")

            # 815
            for bus_label, bus in [("Bus0(ECU)", 0), ("Bus2(MPC)", 2)]:
                raw = latest.get((815, bus))
                if raw:
                    print(f"  815 {bus_label}: {hex_str(raw)} {chk_ok(raw)}")

    except KeyboardInterrupt:
        print("\n诊断结束")


if __name__ == "__main__":
    main()
