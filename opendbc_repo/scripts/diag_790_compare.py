#!/usr/bin/env python3
"""
BYD 790 帧逐字节对比诊断 — OP vs 原厂 MPC

核心问题: EPS 完全忽略 OP 发的 790 帧（MPC_State=2/3, LKAS_Active=1, LKAS_Output≠0）
         EPS 792 始终回复 MainTq=0, Prepared=0, CruiseActivated=0

诊断目标:
  1. 同时捕获 Bus 2 上原厂 MPC 的 790 和 Bus 0 上 OP 的 790 (sendcan)
  2. 逐字节、逐信号对比差异
  3. 找出 OP 帧与原厂帧的所有不同点
  4. 同时监控 792 EPS 响应

关键假设:
  - Bus 2 上的 790 始终是原厂 MPC 发出的（不受 OP 影响）
  - sendcan 中 address=790, src=0 是 OP 发到 Bus 0 的帧
  - 当 OP 激活时，fwd_hook 拦截 MPC 的 790 不让它到 Bus 0
  - 所以 EPS 只看到 OP 的 790

用法:
  python3 /data/openpilot/opendbc_repo/scripts/diag_790_compare.py

操作:
  1. 启动脚本
  2. 挂D档，松刹车，按 ACC ON
  3. 等 MADS 激活
  4. 观察 OP 790 vs MPC 790 的差异
"""

import time
import cereal.messaging as messaging


def decode_790_full(data):
    """完整解码 790 帧所有信号"""
    if len(data) < 8:
        return {}
    b = data
    # LKAS_Output: 16|11@1- signed
    lkas_raw = (b[2] | ((b[3] & 0x07) << 8))
    if lkas_raw > 1023:
        lkas_raw -= 2048
    return {
        "AutoFullBeamState":  (b[0] >> 0) & 0xF,   # bits 0-3
        "LeftLaneState":      (b[0] >> 4) & 0x3,   # bits 4-5
        "LKAS_Config":        (b[0] >> 6) & 0x3,   # bits 6-7
        "SETME2":             (b[1] >> 0) & 0x3,   # bits 8-9
        "ReqHandsOn":         (b[1] >> 2) & 0x1,   # bit 10
        "MPC_State":          (b[1] >> 3) & 0xF,   # bits 11-14
        "AutoFullBeam_OnOff": (b[1] >> 7) & 0x1,   # bit 15
        "LKAS_Output":        lkas_raw,             # bits 16-26
        "LKAS_ReqPrepare":    (b[3] >> 3) & 0x1,   # bit 27
        "LKAS_Active":        (b[3] >> 4) & 0x1,   # bit 28
        "SETME3":             (b[3] >> 5) & 0x1,   # bit 29
        "TSR_OnOff":          (b[3] >> 6) & 0x1,   # bit 30
        "SETME4":             (b[3] >> 7) & 0x1,   # bit 31
        "SETME5":             (b[4] >> 0) & 0x3,   # bits 32-33
        "RightLaneState":     (b[4] >> 2) & 0x3,   # bits 34-35
        "LKAS_State":         (b[4] >> 4) & 0xF,   # bits 36-39
        "TSR_Result":         b[5],                 # bits 40-47
        "LKAS_AlarmType":     (b[6] >> 0) & 0x3,   # bits 48-49
        "SETME7":             (b[6] >> 2) & 0x3,   # bits 50-51
        "COUNTER":            (b[6] >> 4) & 0xF,   # bits 52-55
        "CHECKSUM":           b[7],                 # bits 56-63
    }


def decode_792(data):
    """解码 792 EPS 响应"""
    if len(data) < 8:
        return {}
    b = data
    mt_raw = (b[1] | ((b[2] & 0xF) << 8))
    main_torque = mt_raw - 4096 if mt_raw > 2047 else mt_raw
    sdt_raw = (b[3] | ((b[4] & 0xF) << 8))
    steer_driver = sdt_raw - 4096 if sdt_raw > 2047 else sdt_raw
    return {
        "Prepared":    (b[0] >> 0) & 0x1,
        "CruiseAct":   (b[0] >> 1) & 0x1,
        "TqFail":      (b[0] >> 2) & 0x1,
        "MainTq":      main_torque,
        "DrvTq":       steer_driver,
    }


def byd_checksum(dat):
    return (0xFF - sum(dat[:7])) & 0xFF


def main():
    sm = messaging.SubMaster([
        'can', 'sendcan', 'carControl', 'carState', 'selfdriveStateSP',
    ])

    print("=" * 80)
    print("BYD 790 帧逐字节对比: OP vs 原厂 MPC")
    print("=" * 80)
    print()
    print("等待 latActive=True 后开始对比...")
    print("(非激活时也会显示 MPC 原厂 790 的空闲值作为参考)")
    print()

    t0 = time.monotonic()
    last_mpc_790 = None       # Bus 2 上 MPC 原厂 790
    last_op_790 = None        # sendcan 中 OP 的 790
    last_792 = None           # Bus 0 上 EPS 的 792
    last_print = 0
    lat_active = False
    compare_count = 0

    # 记录 MPC 空闲值（用于对比）
    mpc_idle_signals = None

    while True:
        sm.update(100)
        now = time.monotonic() - t0

        # 获取 latActive 状态
        if sm.valid['carControl']:
            lat_active = sm['carControl'].latActive

        # 收集 Bus 2 上 MPC 原厂 790 和 Bus 0 上 792
        if sm.updated['can']:
            for msg in sm['can']:
                if msg.address == 790 and msg.src == 2:
                    last_mpc_790 = bytes(msg.dat)
                if msg.address == 792 and msg.src == 0:
                    last_792 = bytes(msg.dat)

        # 收集 sendcan 中 OP 的 790
        if sm.updated['sendcan']:
            for msg in sm['sendcan']:
                if msg.address == 790 and msg.src == 0:
                    last_op_790 = bytes(msg.dat)

        # 每 0.5 秒打印
        if (now - last_print) < 0.5:
            continue
        last_print = now

        # 状态行
        mads_state = "?"
        if sm.valid['selfdriveStateSP']:
            mads_state = sm['selfdriveStateSP'].mads.state
        cruise = sm['carState'].cruiseState.available if sm.valid['carState'] else "?"
        gear = sm['carState'].gearShifter if sm.valid['carState'] else "?"
        brake = sm['carState'].brakePressed if sm.valid['carState'] else "?"

        print(f"\n[{now:.1f}s] latActive={lat_active} MADS={mads_state} "
              f"cruise={cruise} gear={gear} brake={brake}")

        # 显示 MPC 原厂 790
        if last_mpc_790:
            mpc_sig = decode_790_full(last_mpc_790)
            mpc_chk_ok = byd_checksum(last_mpc_790) == last_mpc_790[7]

            # 记录空闲值
            if not lat_active and mpc_idle_signals is None and mpc_sig.get("MPC_State") == 0:
                mpc_idle_signals = dict(mpc_sig)

            print(f"  MPC 790 (Bus2): {last_mpc_790.hex()} chk={'OK' if mpc_chk_ok else 'BAD'}")
            # 显示关键信号
            print(f"    AutoFB={mpc_sig['AutoFullBeamState']} LLane={mpc_sig['LeftLaneState']} "
                  f"Config={mpc_sig['LKAS_Config']} SETME2={mpc_sig['SETME2']} "
                  f"HandsOn={mpc_sig['ReqHandsOn']} MPC_St={mpc_sig['MPC_State']} "
                  f"AutoFB_On={mpc_sig['AutoFullBeam_OnOff']}")
            print(f"    LKAS_Out={mpc_sig['LKAS_Output']:>4d} ReqPrep={mpc_sig['LKAS_ReqPrepare']} "
                  f"Active={mpc_sig['LKAS_Active']} SETME3={mpc_sig['SETME3']} "
                  f"TSR={mpc_sig['TSR_OnOff']} SETME4={mpc_sig['SETME4']}")
            print(f"    SETME5={mpc_sig['SETME5']} RLane={mpc_sig['RightLaneState']} "
                  f"State={mpc_sig['LKAS_State']} TSR_Res={mpc_sig['TSR_Result']} "
                  f"Alarm={mpc_sig['LKAS_AlarmType']} SETME7={mpc_sig['SETME7']}")

        # 显示 OP 的 790（仅 latActive 时或有数据时）
        if last_op_790:
            op_sig = decode_790_full(last_op_790)
            op_chk_ok = byd_checksum(last_op_790) == last_op_790[7]

            print(f"  OP  790 (Bus0): {last_op_790.hex()} chk={'OK' if op_chk_ok else 'BAD'}")
            print(f"    AutoFB={op_sig['AutoFullBeamState']} LLane={op_sig['LeftLaneState']} "
                  f"Config={op_sig['LKAS_Config']} SETME2={op_sig['SETME2']} "
                  f"HandsOn={op_sig['ReqHandsOn']} MPC_St={op_sig['MPC_State']} "
                  f"AutoFB_On={op_sig['AutoFullBeam_OnOff']}")
            print(f"    LKAS_Out={op_sig['LKAS_Output']:>4d} ReqPrep={op_sig['LKAS_ReqPrepare']} "
                  f"Active={op_sig['LKAS_Active']} SETME3={op_sig['SETME3']} "
                  f"TSR={op_sig['TSR_OnOff']} SETME4={op_sig['SETME4']}")
            print(f"    SETME5={op_sig['SETME5']} RLane={op_sig['RightLaneState']} "
                  f"State={op_sig['State']} TSR_Res={op_sig['TSR_Result']} "
                  f"Alarm={op_sig['LKAS_AlarmType']} SETME7={op_sig['SETME7']}")

            # 逐字节对比
            if last_mpc_790:
                diffs = []
                for i in range(min(len(last_mpc_790), len(last_op_790))):
                    if i == 6:  # skip counter byte
                        continue
                    if i == 7:  # skip checksum byte
                        continue
                    if last_mpc_790[i] != last_op_790[i]:
                        diffs.append(f"byte[{i}]: MPC=0x{last_mpc_790[i]:02X} OP=0x{last_op_790[i]:02X}")
                if diffs:
                    print(f"  >>> DIFF: {', '.join(diffs)}")
                else:
                    print(f"  >>> MATCH (bytes 0-5 identical)")

                # 逐信号对比（排除 COUNTER 和 CHECKSUM）
                sig_diffs = []
                for key in mpc_sig:
                    if key in ("COUNTER", "CHECKSUM"):
                        continue
                    if mpc_sig[key] != op_sig[key]:
                        sig_diffs.append(f"{key}: MPC={mpc_sig[key]} OP={op_sig[key]}")
                if sig_diffs:
                    print(f"  >>> SIGNAL DIFF: {', '.join(sig_diffs)}")

        # 显示 792 EPS 响应
        if last_792:
            eps = decode_792(last_792)
            print(f"  EPS 792 (Bus0): {last_792.hex()} | "
                  f"MainTq={eps['MainTq']:>4d} DrvTq={eps['DrvTq']:>4d} "
                  f"Prep={eps['Prepared']} CruAct={eps['CruiseAct']} TqFail={eps['TqFail']}")

        compare_count += 1


if __name__ == "__main__":
    main()
