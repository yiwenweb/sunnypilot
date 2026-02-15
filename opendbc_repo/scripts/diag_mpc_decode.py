#!/usr/bin/env python3
"""
BYD MPC 原厂帧解码工具

解码 Bus 2 上 MPC 原厂帧的每个信号值。
Bus 2 上的帧始终是原厂 MPC 发出的（不受 OP 影响）。

操作步骤:
  1. 启动脚本，先观察 ACC 关闭时的空闲值
  2. 按 ACC 开启，观察值变化
  3. 挂 D 档，观察值变化
  4. 按 SET 激活巡航，观察值变化
  5. 关闭 ACC，观察恢复

使用方法:
  python3 /data/openpilot/opendbc_repo/scripts/diag_mpc_decode.py
"""

import time
import cereal.messaging as messaging


def decode_790(dat):
    """解码 790 ACC_MPC_STATE"""
    if len(dat) < 8:
        return {}
    b = dat
    return {
        "AutoFullBeamState": (b[0] >> 0) & 0xF,
        "LeftLaneState":     (b[0] >> 4) & 0x3,
        "LKAS_Config":       (b[0] >> 6) & 0x3,
        "SETME2":            (b[1] >> 0) & 0x3,
        "ReqHandsOn":        (b[1] >> 2) & 0x1,
        "MPC_State":         (b[1] >> 3) & 0xF,
        "AutoFullBeam_OnOff":(b[1] >> 7) & 0x1,
        "LKAS_Output":       ((b[2] | (b[3] << 8)) & 0x7FF) - (2048 if ((b[2] | (b[3] << 8)) & 0x7FF) > 1023 else 0),
        "LKAS_ReqPrepare":   (b[3] >> 3) & 0x1,
        "LKAS_Active":       (b[3] >> 4) & 0x1,
        "TSR_OnOff":         (b[3] >> 6) & 0x1,
        "SETME5":            (b[4] >> 0) & 0x3,
        "RightLaneState":    (b[4] >> 2) & 0x3,
        "LKAS_State":        (b[4] >> 4) & 0xF,
        "TSR_Result_raw":    b[5],
        "LKAS_AlarmType":    (b[6] >> 0) & 0x3,  # bits 48-49
        "SETME7":            (b[6] >> 2) & 0x3,  # bits 50-51
        "COUNTER":           (b[6] >> 4) & 0xF,  # bits 52-55
        "CHECKSUM":          b[7],
    }


def decode_813(dat):
    """解码 813 ACC_HUD_ADAS"""
    if len(dat) < 8:
        return {}
    b = dat
    # SetSpeed: 0|9@1+ scale=0.5
    set_speed_raw = (b[0] | ((b[1] & 0x1) << 8))
    return {
        "SetSpeed":       set_speed_raw * 0.5,
        "HasLead":        (b[1] >> 1) & 0x1,
        "SetDistance":     (b[1] >> 2) & 0x7,
        "LeadingDist":    (b[1] >> 5) & 0x7,
        "AEB":            (b[2] >> 0) & 0x1,
        "FCW":            (b[2] >> 1) & 0x1,
        "SETME1":         (b[2] >> 2) & 0x1,
        "AccState":       (b[2] >> 3) & 0x7,
        "AccOn1":         (b[2] >> 6) & 0x1,
        "CloseWarning":   (b[2] >> 7) & 0x1,
        "SETME2":         (b[3] >> 0) & 0x1,
        "Notify":         (b[3] >> 1) & 0x7F,
        "Status":         (b[4] >> 0) & 0xF,
        "SETME3_lo4":     (b[4] >> 4) & 0xF,
        "SETME3_hi8":     b[5],
        "COUNTER":        (b[6] >> 0) & 0xF,
        "SETME4":         (b[6] >> 4) & 0xF,
        "CHECKSUM":       b[7],
    }


def decode_814(dat):
    """解码 814 ACC_CMD"""
    if len(dat) < 8:
        return {}
    b = dat
    accel_raw = b[0]
    cbu_raw = b[1]
    cbl_raw = b[2]
    return {
        "AccelCmd":           accel_raw * 0.05 - 5.0,
        "AccelCmd_raw":       accel_raw,
        "ComfortBandUpper":   cbu_raw * 0.05 - 5.0,
        "CBU_raw":            cbu_raw,
        "ComfortBandLower":   cbl_raw * 0.05 - 5.0,
        "CBL_raw":            cbl_raw,
        "JerkUpper_raw":      (b[3] >> 0) & 0x7F,
        "JerkUpper":          ((b[3] >> 0) & 0x7F) * 0.2,
        "SETME1":             (b[3] >> 7) & 0x1,
        "JerkLower_raw":      (b[4] >> 0) & 0x7F,
        "JerkLower":          ((b[4] >> 0) & 0x7F) * 0.2 - 16.0,
        "ResumeFromStandstill": (b[4] >> 7) & 0x1,
        "StandstillState":    (b[5] >> 0) & 0x1,
        "BrakeBehaviour":     (b[5] >> 1) & 0x3,
        "AccReqNotStandstill":(b[5] >> 3) & 0x1,
        "AccControlActive":   (b[5] >> 4) & 0x1,
        "AccOverrideOrStandstill": (b[5] >> 5) & 0x1,
        "EspBehaviour":       (b[5] >> 6) & 0x3,
        "byte5_hex":          f"0x{b[5]:02X}",
        "COUNTER":            (b[6] >> 0) & 0xF,
        "SETME2":             (b[6] >> 4) & 0xF,
        "CHECKSUM":           b[7],
    }


def decode_815(dat):
    """解码 815 ACC_AEB"""
    if len(dat) < 8:
        return {}
    b = dat
    return {
        "AEB_Active":    (b[0] >> 0) & 0x1,
        "byte0":         f"0x{b[0]:02X}",
        "AEB_Decel_raw": b[1],
        "AEB_Decel":     b[1] * 0.05,
        "byte2":         f"0x{b[2]:02X}",
        "byte3":         f"0x{b[3]:02X}",
        "byte4":         f"0x{b[4]:02X}",
        "byte5":         f"0x{b[5]:02X}",
        "COUNTER":       (b[6] >> 0) & 0xF,
        "SETME":         (b[6] >> 4) & 0xF,
        "CHECKSUM":      b[7],
    }


def decode_792(dat):
    """解码 792 ACC_EPS_STATE"""
    if len(dat) < 8:
        return {}
    b = dat
    # MainTorque: 8|12@1- signed
    mt_raw = (b[1] | ((b[2] & 0xF) << 8))
    main_torque = mt_raw - 4096 if mt_raw > 2047 else mt_raw
    # SteerDriverTorque: 24|12@1- signed
    sdt_raw = (b[3] | ((b[4] & 0xF) << 8))
    steer_driver = sdt_raw - 4096 if sdt_raw > 2047 else sdt_raw
    return {
        "LKAS_Prepared":   (b[0] >> 0) & 0x1,
        "CruiseActivated": (b[0] >> 1) & 0x1,
        "TorqueFailed":    (b[0] >> 2) & 0x1,
        "SETME1":          (b[0] >> 3) & 0x1,
        "SteerWarning":    (b[0] >> 4) & 0x1,
        "SteerErrorCode":  (b[0] >> 5) & 0x7,
        "byte0":           f"0x{b[0]:02X}",
        "MainTorque":      main_torque,
        "HandsOff":        (b[2] >> 5) & 0x1,
        "SteerDriverTorque": steer_driver,
        "COUNTER":         (b[6] >> 4) & 0xF,
        "CHECKSUM":        b[7],
    }


def hex_str(data):
    return " ".join(f"{b:02x}" for b in data)


def fmt_signals(signals, highlight_keys=None):
    """格式化信号输出，高亮变化的字段"""
    parts = []
    for k, v in signals.items():
        if k in ("CHECKSUM", "COUNTER"):
            continue
        if highlight_keys and k in highlight_keys:
            parts.append(f"**{k}={v}**")
        else:
            parts.append(f"{k}={v}")
    return "  ".join(parts)


def find_changes(prev, curr):
    """找出变化的字段"""
    if prev is None:
        return set()
    changed = set()
    for k in curr:
        if k in ("CHECKSUM", "COUNTER"):
            continue
        if k not in prev or prev[k] != curr[k]:
            changed.add(k)
    return changed


def main():
    sm = messaging.SubMaster(['can', 'carState', 'carControl', 'selfdriveState'])

    DECODERS = {
        790: ("790_MPC_STATE", decode_790),
        813: ("813_ACC_HUD",   decode_813),
        814: ("814_ACC_CMD",   decode_814),
        815: ("815_ACC_AEB",   decode_815),
        792: ("792_EPS_STATE", decode_792),
    }

    # 上一次的信号值（用于检测变化）
    prev_signals = {}
    # 最新原始帧
    latest_raw = {}

    start = time.monotonic()
    last_report = 0

    print("=" * 75)
    print("BYD MPC 原厂帧解码 — Bus 2 信号值实时监控")
    print("=" * 75)
    print("步骤: 1.观察空闲值 → 2.按ACC → 3.挂D档 → 4.按SET → 5.关ACC")
    print("变化的字段会用 ** 标记")
    print()

    try:
        while True:
            sm.update(100)
            if not sm.updated['can']:
                continue

            now = time.monotonic() - start

            # 收集 Bus 2 上的帧（MPC 原厂）和 Bus 0 上的 792（EPS 真实）
            for msg in sm['can']:
                bus = msg.src
                addr = msg.address
                if addr in DECODERS:
                    if (addr == 792 and bus == 0) or (addr != 792 and bus == 2):
                        latest_raw[addr] = bytes(msg.dat)

            # 每 2 秒报告
            if now - last_report < 2.0:
                continue
            last_report = now

            # 状态行
            avail = ""
            lat = ""
            if sm.valid['carState']:
                cs = sm['carState']
                avail = f"ACC={'ON' if cs.cruiseState.available else 'OFF'}"
            if sm.valid['carControl']:
                cc = sm['carControl']
                lat = f"lat={'Y' if cc.latActive else 'N'} long={'Y' if cc.longActive else 'N'}"

            print(f"\n[{now:.0f}s] {avail} {lat}")

            # 解码并输出每个帧
            for addr in [790, 813, 814, 815, 792]:
                raw = latest_raw.get(addr)
                if raw is None:
                    continue

                name, decoder = DECODERS[addr]
                signals = decoder(raw)
                changed = find_changes(prev_signals.get(addr), signals)
                prev_signals[addr] = signals

                # 原始字节
                print(f"  {name}: {hex_str(raw)}")
                # 解码信号（只显示关键字段，变化的用 ** 标记）
                parts = []
                for k, v in signals.items():
                    if k in ("CHECKSUM", "COUNTER"):
                        continue
                    if k in changed:
                        parts.append(f">>>{k}={v}<<<")
                    else:
                        parts.append(f"{k}={v}")
                # 分行显示，每行不超过 80 字符
                line = "    "
                for p in parts:
                    if len(line) + len(p) + 2 > 80:
                        print(line)
                        line = "    "
                    line += p + "  "
                if line.strip():
                    print(line)

    except KeyboardInterrupt:
        print("\n\n=== 最终状态汇总 ===")
        for addr in [790, 813, 814, 815, 792]:
            raw = latest_raw.get(addr)
            if raw is None:
                continue
            name, decoder = DECODERS[addr]
            signals = decoder(raw)
            print(f"\n{name}: {hex_str(raw)}")
            for k, v in signals.items():
                print(f"  {k}: {v}")
        print("\n诊断结束")


if __name__ == "__main__":
    main()
