#!/usr/bin/env python3
"""
BYD 横向控制诊断工具 — 路测前检查

在 openpilot 运行状态下执行，检查横向控制链路是否正常：
  1. panda 安全层状态（controls_allowed_lat, acc_main_on 等）
  2. openpilot 是否在发送 790/813/814/815 到 Bus 0
  3. EPS 是否在 792 中反馈（MainTorque, LKAS_Prepared）
  4. fwd_hook 是否正确拦截 MPC 的 790（Bus 2→Bus 0）
  5. 校验和是否正确

使用方法（openpilot 运行中）：
  python3 /data/openpilot/opendbc_repo/scripts/diag_lat_control.py

  或者先按 ACC 开启横向，再运行此脚本
"""

import time
import cereal.messaging as messaging

TARGET_ADDRS = {
    790: "ACC_MPC_STATE",
    792: "ACC_EPS_STATE",
    813: "ACC_HUD_ADAS",
    814: "ACC_CMD",
    815: "ACC_AEB",
}


def verify_checksum(data: bytes) -> bool:
    """验证校验和: sum(all 8 bytes) & 0xFF == 0xFF"""
    if len(data) < 8:
        return False
    return sum(data[:8]) & 0xFF == 0xFF


def decode_790(data: bytes) -> dict:
    if len(data) < 8:
        return {}
    return {
        "LKAS_Output": ((data[2] | (data[3] << 8)) & 0x7FF) - 2048
                       if ((data[2] | (data[3] << 8)) & 0x7FF) > 1023
                       else (data[2] | (data[3] << 8)) & 0x7FF,
        "LKAS_Active": (data[3] >> 4) & 0x1,
        "LKAS_ReqPrepare": (data[3] >> 3) & 0x1,
        "COUNTER": (data[6] >> 4) & 0xF,
    }


def decode_792(data: bytes) -> dict:
    if len(data) < 8:
        return {}
    main_torque_raw = (data[1] | ((data[2] & 0x0F) << 8))
    if main_torque_raw > 2047:
        main_torque_raw -= 4096
    driver_torque_raw = (data[3] | ((data[4] & 0x0F) << 8))
    if driver_torque_raw > 2047:
        driver_torque_raw -= 4096
    return {
        "LKAS_Prepared": data[0] & 0x1,
        "CruiseActivated": (data[0] >> 1) & 0x1,
        "TorqueFailed": (data[0] >> 2) & 0x1,
        "SteerWarning": (data[0] >> 4) & 0x1,
        "SteerErrorCode": (data[0] >> 5) & 0x7,
        "MainTorque": main_torque_raw,
        "DriverTorque": driver_torque_raw,
        "COUNTER": (data[6] >> 4) & 0xF,
    }


def decode_813(data: bytes) -> dict:
    if len(data) < 8:
        return {}
    return {
        "AccState": (data[2] >> 3) & 0x7,
        "AccOn1": (data[2] >> 6) & 0x1,
        "Status": data[4] & 0xF,
        "COUNTER": data[6] & 0xF,
    }


def main():
    sm = messaging.SubMaster(['can', 'pandaStates', 'selfdriveState', 'carControl', 'carState'])

    # 统计: frames[bus][addr] = {"count": N, "last_data": bytes, "last_ts": float}
    frames = {0: {}, 2: {}}
    start_time = time.monotonic()

    print("=" * 70)
    print("BYD 横向控制诊断工具")
    print("=" * 70)
    print()
    print("请确保 openpilot 正在运行")
    print("按 ACC 按钮开启横向控制，然后观察输出")
    print("Ctrl+C 退出")
    print()

    try:
        while True:
            sm.update(100)

            # 收集 CAN 帧
            if sm.updated['can']:
                for msg in sm['can']:
                    bus = msg.src
                    addr = msg.address
                    if addr not in TARGET_ADDRS:
                        continue
                    if bus not in (0, 2):
                        continue
                    if addr not in frames[bus]:
                        frames[bus][addr] = {"count": 0, "last_data": b"", "first_ts": time.monotonic() - start_time}
                    frames[bus][addr]["count"] += 1
                    frames[bus][addr]["last_data"] = bytes(msg.dat)
                    frames[bus][addr]["last_ts"] = time.monotonic() - start_time

            elapsed = time.monotonic() - start_time
            if elapsed < 1.0:
                continue

            # 每 2 秒输出一次诊断
            if int(elapsed * 10) % 20 != 0:
                continue

            print(f"\n{'='*70}")
            print(f"  [{elapsed:.0f}s] 诊断报告")
            print(f"{'='*70}")

            # === 1. openpilot 状态 ===
            if sm.updated['selfdriveState'] or sm.valid['selfdriveState']:
                ss = sm['selfdriveState']
                print(f"\n  [openpilot 状态]")
                print(f"    enabled={ss.enabled}  active={ss.active}"
                      f"  state={ss.state}  engageable={ss.engageable}")

            if sm.updated['carControl'] or sm.valid['carControl']:
                cc = sm['carControl']
                print(f"    CC.enabled={cc.enabled}  latActive={cc.latActive}"
                      f"  longActive={cc.longActive}")
                if hasattr(cc, 'actuators'):
                    print(f"    torque={cc.actuators.torque:.3f}"
                          f"  torqueOutputCan={cc.actuators.torqueOutputCan}")

            if sm.updated['carState'] or sm.valid['carState']:
                car = sm['carState']
                print(f"    cruiseAvailable={car.cruiseState.available}"
                      f"  cruiseEnabled={car.cruiseState.enabled}")
                print(f"    steeringTorque={car.steeringTorque:.0f}"
                      f"  steeringTorqueEps={car.steeringTorqueEps:.0f}"
                      f"  steeringPressed={car.steeringPressed}")
                print(f"    vEgo={car.vEgo:.1f} m/s ({car.vEgo*3.6:.0f} km/h)"
                      f"  brakePressed={car.brakePressed}")

            # === 2. panda 状态 ===
            if sm.updated['pandaStates'] or sm.valid['pandaStates']:
                for ps in sm['pandaStates']:
                    print(f"\n  [panda 安全层]")
                    print(f"    safetyModel={ps.safetyModel}"
                          f"  controlsAllowed={ps.controlsAllowed}")
                    if hasattr(ps, 'controlsAllowedLat'):
                        print(f"    controlsAllowedLat={ps.controlsAllowedLat}")

            # === 3. CAN 帧统计 ===
            print(f"\n  [CAN 帧统计]")

            # Bus 0 — openpilot 发送的帧
            print(f"    --- Bus 0 (车辆主总线 / openpilot TX) ---")
            for addr in sorted(TARGET_ADDRS.keys()):
                if addr in frames[0]:
                    f = frames[0][addr]
                    dt = f["last_ts"] - f["first_ts"]
                    hz = f["count"] / dt if dt > 0 else 0
                    chk = "✓" if verify_checksum(f["last_data"]) else "✗"
                    line = (f"    {TARGET_ADDRS[addr]:>16}({addr}): "
                            f"{f['count']:>5}帧  {hz:.0f}Hz  校验{chk}")

                    # 解码关键信号
                    if addr == 790:
                        d = decode_790(f["last_data"])
                        line += (f"  LKAS_Out={d.get('LKAS_Output',0)}"
                                 f"  Active={d.get('LKAS_Active',0)}"
                                 f"  CNT={d.get('COUNTER',0)}")
                    elif addr == 792:
                        d = decode_792(f["last_data"])
                        line += (f"  MainTorque={d.get('MainTorque',0)}"
                                 f"  Prepared={d.get('LKAS_Prepared',0)}"
                                 f"  CruiseAct={d.get('CruiseActivated',0)}"
                                 f"  CNT={d.get('COUNTER',0)}")
                    elif addr == 813:
                        d = decode_813(f["last_data"])
                        line += (f"  AccState={d.get('AccState',0)}"
                                 f"  Status={d.get('Status',0)}")
                    print(line)
                else:
                    if addr in (790, 813, 814, 815):
                        print(f"    {TARGET_ADDRS[addr]:>16}({addr}): ❌ 未检测到")

            # Bus 2 — 原厂 MPC 帧
            print(f"    --- Bus 2 (原厂 MPC) ---")
            for addr in sorted(TARGET_ADDRS.keys()):
                if addr in frames[2]:
                    f = frames[2][addr]
                    dt = f["last_ts"] - f["first_ts"]
                    hz = f["count"] / dt if dt > 0 else 0
                    chk = "✓" if verify_checksum(f["last_data"]) else "✗"
                    print(f"    {TARGET_ADDRS[addr]:>16}({addr}): "
                          f"{f['count']:>5}帧  {hz:.0f}Hz  校验{chk}")
                else:
                    if addr in (790, 813, 814, 815):
                        print(f"    {TARGET_ADDRS[addr]:>16}({addr}): 未收到"
                              f"  (正常=被fwd_hook拦截 / 异常=MPC未发送)")

            # === 4. 诊断结论 ===
            print(f"\n  [诊断结论]")
            issues = []

            # 检查 openpilot 是否在发送 790
            if 790 not in frames[0]:
                issues.append("❌ Bus 0 无 790 — openpilot 未发送转向控制")
                issues.append("   可能原因: controls_allowed_lat=false, 未按ACC, 或 panda 拒绝TX")
            else:
                d790 = decode_790(frames[0][790]["last_data"])
                if d790.get("LKAS_Active", 0) == 0:
                    issues.append("⚠️  790 LKAS_Active=0 — 横向控制未激活（可能未按ACC或latActive=false）")
                else:
                    issues.append("✅ 790 LKAS_Active=1 — 横向控制已激活")

                if not verify_checksum(frames[0][790]["last_data"]):
                    issues.append("❌ 790 校验和错误!")

            # 检查 EPS 反馈
            if 792 in frames[0]:
                d792 = decode_792(frames[0][792]["last_data"])
                if d792.get("MainTorque", 0) != 0:
                    issues.append(f"✅ 792 MainTorque={d792['MainTorque']} — EPS 正在执行转向 (E.T.值)")
                else:
                    if 790 in frames[0] and decode_790(frames[0][790]["last_data"]).get("LKAS_Active", 0) == 1:
                        issues.append("⚠️  792 MainTorque=0 — EPS 未响应转向请求")
                        issues.append("   可能原因: EPS 未收到完整ACC报文组, 或 LKAS_Prepared 未就绪")
                    else:
                        issues.append("✅ 792 MainTorque=0 — 正常（横向未激活）")
                if d792.get("LKAS_Prepared", 0) == 1:
                    issues.append("✅ 792 LKAS_Prepared=1 — EPS 准备就绪")
            else:
                issues.append("⚠️  Bus 0 无 792 — EPS 未发送反馈（可能正常，等待更多数据）")

            # 检查 813/814/815
            for addr in (813, 814, 815):
                if addr in frames[0]:
                    if not verify_checksum(frames[0][addr]["last_data"]):
                        issues.append(f"❌ {addr} 校验和错误!")
                    else:
                        issues.append(f"✅ {addr} 校验和正确")

            # 检查 fwd_hook 拦截
            if 790 in frames[0] and 790 in frames[2]:
                issues.append("⚠️  Bus 0 和 Bus 2 都有 790 — fwd_hook 可能未拦截 MPC")
            elif 790 in frames[0] and 790 not in frames[2]:
                issues.append("✅ fwd_hook 正常 — MPC 的 790 被拦截")

            for issue in issues:
                print(f"    {issue}")

            # 重置统计
            frames = {0: {}, 2: {}}
            start_time = time.monotonic()

    except KeyboardInterrupt:
        print("\n\n诊断结束")


if __name__ == "__main__":
    main()
