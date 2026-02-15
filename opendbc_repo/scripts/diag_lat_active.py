#!/usr/bin/env python3
"""诊断横向控制激活后的实际效果

当 CC.latActive=True 时:
1. carcontroller 是否在发 790 帧？
2. 790 帧的内容是什么？(LKAS_Output, LKAS_Active, MPC_State, LKAS_ReqPrepare)
3. EPS 792 的响应？(MainTorque, LKAS_Prepared, CruiseActivated)
4. steeringTorqueEps 是否非零？

用法: openpilot 运行时 SSH 到 C3:
  python3 /data/openpilot/opendbc_repo/scripts/diag_lat_active.py

操作步骤:
  1. 启动脚本
  2. 挂D档，松刹车
  3. 按 ACC ON
  4. 等 MADS 激活 (wrongGear 消失后自动激活)
  5. 观察 790/792 帧内容
"""

import time
import cereal.messaging as messaging

def decode_790(data):
    """解码 790 (ACC_MPC_STATE) 帧"""
    if len(data) < 8:
        return {}
    b = data
    # LKAS_Output: bits 16-26 (11-bit signed), byte2 low 8 + byte3 low 3
    lkas_raw = (b[2] | ((b[3] & 0x07) << 8))
    if lkas_raw > 1023:
        lkas_raw -= 2048
    # LKAS_Active: bit 28 = byte3 bit4
    lkas_active = (b[3] >> 4) & 1
    # LKAS_ReqPrepare: bit 29 = byte3 bit5
    lkas_req_prepare = (b[3] >> 5) & 1
    # MPC_State: bits 12-13 = byte1 bits 4-5
    mpc_state = (b[1] >> 4) & 0x3
    # COUNTER: byte6 high nibble
    counter = (b[6] >> 4) & 0xF
    return {
        'LKAS_Output': lkas_raw,
        'LKAS_Active': lkas_active,
        'LKAS_ReqPrepare': lkas_req_prepare,
        'MPC_State': mpc_state,
        'counter': counter,
    }

def decode_792(data):
    """解码 792 (ACC_EPS_STATE) 帧"""
    if len(data) < 8:
        return {}
    b = data
    # MainTorque: bits 8-19 (12-bit signed)
    main_torque = (b[1] | ((b[2] & 0x0F) << 8))
    if main_torque > 2047:
        main_torque -= 4096
    # SteerDriverTorque: bits 24-35 (12-bit signed)
    drv_torque = (b[3] | ((b[4] & 0x0F) << 8))
    if drv_torque > 2047:
        drv_torque -= 4096
    # LKAS_Prepared: bit 0
    lkas_prepared = b[0] & 1
    # CruiseActivated: bit 1
    cruise_activated = (b[0] >> 1) & 1
    # TorqueFailed: bit 2
    torque_failed = (b[0] >> 2) & 1
    counter = (b[6] >> 4) & 0xF
    return {
        'MainTorque': main_torque,
        'DriverTorque': drv_torque,
        'LKAS_Prepared': lkas_prepared,
        'CruiseActivated': cruise_activated,
        'TorqueFailed': torque_failed,
        'counter': counter,
    }

def main():
    sm = messaging.SubMaster([
        'carState', 'carControl', 'carOutput', 'selfdriveStateSP',
        'sendcan', 'can', 'pandaStates',
    ])

    print("=" * 78)
    print("BYD 横向控制实际效果诊断")
    print("=" * 78)
    print("等待 CC.latActive=True ...\n")

    t0 = time.monotonic()
    lat_active_start = None
    prev_lat_active = False
    frame_count = 0
    tx_790_count = 0
    last_790_data = None
    last_792_data = None
    last_print = 0

    while True:
        sm.update(100)
        now = time.monotonic() - t0

        cc = sm['carControl']
        cs = sm['carState']
        sp = sm['selfdriveStateSP']
        mads = sp.mads

        lat_active = cc.latActive

        # 检测 latActive 变化
        if lat_active and not prev_lat_active:
            lat_active_start = now
            tx_790_count = 0
            print(f"\n[{now:.3f}s] === latActive ON === gear={cs.gearShifter} brake={cs.brakePressed}")
        elif not lat_active and prev_lat_active:
            duration = now - lat_active_start if lat_active_start else 0
            print(f"\n[{now:.3f}s] === latActive OFF === (was active {duration:.1f}s, sent {tx_790_count} x 790)")
        prev_lat_active = lat_active

        # 解析 sendcan 中的 790 帧
        if sm.updated['sendcan'] and lat_active:
            for msg in sm['sendcan']:
                if msg.address == 790 and msg.busTime == 0:  # Bus 0
                    tx_790_count += 1
                    last_790_data = bytes(msg.dat)

        # 解析 can 中的 792 帧 (Bus 0, 来自真实 EPS)
        if sm.updated['can']:
            for msg in sm['can']:
                if msg.address == 792 and msg.src == 0:
                    last_792_data = bytes(msg.dat)

        # latActive 时每 0.5 秒打印一次详细状态
        if lat_active and (now - last_print) >= 0.5:
            last_print = now
            elapsed = now - lat_active_start if lat_active_start else 0

            # carOutput 实际输出
            co = sm['carOutput'] if sm.valid['carOutput'] else None
            torque_out = co.actuatorsOutput.torqueOutputCan if co else '?'
            torque_req = cc.actuators.torque

            # panda CA
            ca = '?'
            ca_lat = '?'
            if sm.valid['pandaStates'] and len(sm['pandaStates']) > 0:
                ps = sm['pandaStates'][0]
                ca = ps.controlsAllowed

            print(f"[{now:.1f}s] +{elapsed:.1f}s | "
                  f"torque_req={torque_req:.3f} torque_out={torque_out} | "
                  f"steerEps={cs.steeringTorqueEps:.0f} steerDrv={cs.steeringTorque:.0f} | "
                  f"CA={ca} MADS={mads.state}")

            if last_790_data:
                d = decode_790(last_790_data)
                print(f"  TX 790: LKAS_Out={d['LKAS_Output']:>4d} Active={d['LKAS_Active']} "
                      f"ReqPrep={d['LKAS_ReqPrepare']} MPC_St={d['MPC_State']} "
                      f"cnt={d['counter']} raw={last_790_data.hex()}")

            if last_792_data:
                d = decode_792(last_792_data)
                print(f"  RX 792: MainTq={d['MainTorque']:>4d} DrvTq={d['DriverTorque']:>4d} "
                      f"Prepared={d['LKAS_Prepared']} CruiseAct={d['CruiseActivated']} "
                      f"TqFail={d['TorqueFailed']} cnt={d['counter']} raw={last_792_data.hex()}")

        # 非激活时每3秒打印摘要
        if not lat_active and int(now) % 3 == 0 and int(now * 10) % 30 == 0:
            print(f"[{now:.0f}s] waiting... MADS={mads.state} cruise={cs.cruiseState.available} "
                  f"gear={cs.gearShifter} brake={cs.brakePressed}")

        frame_count += 1

if __name__ == "__main__":
    main()
