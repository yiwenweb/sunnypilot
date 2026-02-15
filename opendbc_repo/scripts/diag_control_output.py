#!/usr/bin/env python3
"""
BYD 控制输出诊断 — 检查 carcontroller 是否在发送帧以及帧内容

检查项:
1. CC.latActive / CC.longActive 是否为 True
2. actuators.torque / actuators.accel 的值
3. sendcan 中是否有 790/813/814/815 帧
4. 790 帧的 LKAS_Output 和 LKAS_Active 值
5. Bus 0 上实际收到的 790 帧（确认 fwd_hook 拦截+替换）

用法: python3 /data/openpilot/opendbc_repo/scripts/diag_control_output.py
"""

import time
import cereal.messaging as messaging


def decode_790(dat):
    """解码 790 ACC_MPC_STATE"""
    if len(dat) < 8:
        return {}
    # LKAS_Output: bits 16-26, 11-bit signed
    lkas_output = ((dat[2] | (dat[3] << 8)) & 0x7FF)
    if lkas_output > 1023:
        lkas_output -= 2048
    # LKAS_Active: bit 28
    lkas_active = (dat[3] >> 4) & 1
    # LKAS_ReqPrepare: bit 27
    lkas_req = (dat[3] >> 3) & 1
    # Counter: bits 52-55 (high nibble of byte 6)
    counter = (dat[6] >> 4) & 0xF
    return {
        'LKAS_Output': lkas_output,
        'LKAS_Active': lkas_active,
        'LKAS_ReqPrepare': lkas_req,
        'counter': counter,
    }


def decode_814(dat):
    """解码 814 ACC_CMD"""
    if len(dat) < 8:
        return {}
    accel_raw = dat[0]
    accel = accel_raw * 0.05 - 5.0
    esp_behaviour = (dat[5] >> 6) & 0x3
    acc_control_active = (dat[5] >> 4) & 1
    acc_req_not_standstill = (dat[5] >> 3) & 1
    counter = dat[6] & 0xF
    return {
        'AccelCmd': round(accel, 2),
        'AccelRaw': accel_raw,
        'EspBehaviour': esp_behaviour,
        'AccControlActive': acc_control_active,
        'AccReqNotStandstill': acc_req_not_standstill,
        'counter': counter,
    }


def main():
    print("=" * 78)
    print("BYD 控制输出诊断")
    print("=" * 78)

    sm = messaging.SubMaster([
        'carState', 'carControl', 'selfdriveState', 'pandaStates',
        'sendcan', 'controlsState',
    ])

    start = time.monotonic()
    last_report = 0
    frame_count_790 = 0
    frame_count_814 = 0
    last_790 = {}
    last_814 = {}

    try:
        while True:
            sm.update(10)
            now = time.monotonic() - start

            # 检查 sendcan 中的帧
            if sm.updated['sendcan']:
                for msg in sm['sendcan']:
                    addr = msg.address
                    bus = msg.src
                    dat = bytes(msg.dat)
                    if addr == 790 and bus == 0:
                        frame_count_790 += 1
                        last_790 = decode_790(dat)
                        last_790['raw'] = dat.hex()
                    elif addr == 814 and bus == 0:
                        frame_count_814 += 1
                        last_814 = decode_814(dat)
                        last_814['raw'] = dat.hex()

            # 每2秒报告
            if now - last_report < 2.0:
                continue
            last_report = now

            # carControl 状态
            if sm.valid['carControl']:
                cc = sm['carControl']
                act = cc.actuators
                print(f"\n[{now:.0f}s] CC: latActive={cc.latActive} longActive={cc.longActive}"
                      f" enabled={cc.enabled}")
                print(f"  actuators: torque={act.torque:.3f} accel={act.accel:.2f}"
                      f" torqueOutputCan={act.torqueOutputCan}")

            # controlsState (横向控制器输出)
            if sm.valid['controlsState']:
                cs_ctrl = sm['controlsState']
                lat = cs_ctrl.lateralControlState
                which = lat.which()
                if which == 'torqueState':
                    ts = lat.torqueState
                    print(f"  latCtrl: output={ts.output:.3f} active={ts.active}"
                          f" saturated={ts.saturated} error={ts.error:.3f}")
                print(f"  curvature={cs_ctrl.curvature:.4f}"
                      f" desiredCurvature={cs_ctrl.desiredCurvature:.4f}")

            # carState
            if sm.valid['carState']:
                cs = sm['carState']
                print(f"  CS: vEgo={cs.vEgo:.2f} steerAngle={cs.steeringAngleDeg:.1f}"
                      f" steerTorque={cs.steeringTorque:.0f}"
                      f" steerTorqueEps={cs.steeringTorqueEps:.0f}")

            # selfdriveState
            if sm.valid['selfdriveState']:
                sds = sm['selfdriveState']
                print(f"  SDS: enabled={sds.enabled} state={sds.state}")

            # sendcan 帧统计
            print(f"  sendcan: 790 count={frame_count_790} 814 count={frame_count_814}")
            if last_790:
                print(f"  last 790: {last_790}")
            if last_814:
                print(f"  last 814: {last_814}")

            # panda
            if sm.valid['pandaStates']:
                for ps in sm['pandaStates']:
                    if str(ps.safetyModel) != 'silent':
                        print(f"  PANDA: CA={ps.controlsAllowed}"
                              f" rxInvalid={ps.safetyRxChecksInvalid}")

    except KeyboardInterrupt:
        print("\n诊断结束")


if __name__ == "__main__":
    main()
