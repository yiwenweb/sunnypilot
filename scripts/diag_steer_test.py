#!/usr/bin/env python3
"""实时监控 EPS 响应 — 验证转向控制是否生效

监控:
1. 790 (ACC_MPC_STATE) — openpilot 发送的转向指令
2. 792 (ACC_EPS_STATE) — EPS 的响应
3. carControl.latActive — 横向控制是否激活

用法: openpilot 运行时 SSH 到 C3:
  python3 /data/openpilot/scripts/diag_steer_test.py
"""
import sys
import struct
sys.path.insert(0, '/data/openpilot')

import cereal.messaging as messaging

def decode_790(dat):
    """解码 ACC_MPC_STATE (790)"""
    if len(dat) < 8:
        return {}
    b = dat
    # LKAS_Output: bits 16-26, 11-bit signed
    lkas_raw = ((b[2] | (b[3] << 8)) & 0x7FF)
    if lkas_raw > 1023:
        lkas_raw -= 2048
    # LKAS_Active: bit 28
    active = (b[3] >> 4) & 1
    # LKAS_ReqPrepare: bit 27
    req_prepare = (b[3] >> 3) & 1
    # LKAS_Config: bits 9-10
    config = (b[1] >> 1) & 3
    # LKAS_State: bits 48-50
    state = b[6] & 7
    # COUNTER: bits 52-55
    counter = (b[6] >> 4) & 0xF
    return {
        'output': lkas_raw,
        'active': active,
        'prepare': req_prepare,
        'config': config,
        'state': state,
        'cnt': counter,
    }

def decode_792(dat):
    """解码 ACC_EPS_STATE (792)"""
    if len(dat) < 8:
        return {}
    b = dat
    # LKAS_Prepared: bit 0
    prepared = b[0] & 1
    # CruiseActivated: bit 1
    cruise_act = (b[0] >> 1) & 1
    # TorqueFailed: bit 2
    torque_fail = (b[0] >> 2) & 1
    # SteerWarning: bit 4
    steer_warn = (b[0] >> 4) & 1
    # MainTorque: bits 12-22, 11-bit signed
    main_torque = ((b[1] >> 4) | (b[2] << 4)) & 0x7FF
    if main_torque > 1023:
        main_torque -= 2048
    # SteerDriverTorque: bits 24-35, 12-bit signed
    driver_torque = (b[3] | (b[4] << 8)) & 0xFFF
    if driver_torque > 2047:
        driver_torque -= 4096
    return {
        'prepared': prepared,
        'cruise': cruise_act,
        'fail': torque_fail,
        'warn': steer_warn,
        'main_t': main_torque,
        'drv_t': driver_torque,
    }

def main():
    sm = messaging.SubMaster(['can', 'carControl', 'carState'])

    print("=== EPS 转向响应监控 ===")
    print("等待数据...")

    # 等待 carState 先到
    for _ in range(50):
        sm.update(100)
        if sm.updated['carState']:
            break

    # 从 Params 直接读 carParams（避免 50 秒发布周期问题）
    from cereal import car
    from openpilot.common.params import Params
    params = Params()
    cp_raw = params.get("CarParams")
    if cp_raw:
        with car.CarParams.from_bytes(cp_raw) as cp:
            print(f"brand={cp.brand} fp={cp.carFingerprint} safety={cp.safetyConfigs[0].safetyModel if cp.safetyConfigs else '?'}")
            print(f"steerAtStandstill={cp.steerAtStandstill} altExp={cp.alternativeExperience}")
    else:
        print("*** CarParams 未找到!")

    print()
    print("格式: 790(发送) → 792(EPS响应) | carControl")
    print("-" * 100)

    last_790 = {}
    last_792 = {}

    try:
        while True:
            sm.update(50)

            if sm.updated['can']:
                for msg in sm['can']:
                    bus = msg.src
                    addr = msg.address
                    dat = msg.dat

                    if addr == 790 and bus == 0:
                        last_790 = decode_790(dat)
                    elif addr == 792 and bus == 0:
                        last_792 = decode_792(dat)
                    # bus 128 = returned, bus 192 = rejected
                    elif addr == 790 and bus == 128:
                        last_790['returned'] = True
                    elif addr == 790 and bus == 192:
                        last_790['rejected'] = True

            if sm.updated['carControl']:
                cc = sm['carControl']
                cs = sm['carState']

                r790 = last_790
                r792 = last_792

                status = ""
                if r790.get('rejected'):
                    status = " *** 790 REJECTED ***"
                    last_790.pop('rejected', None)

                line = (
                    f"790: out={r790.get('output','-'):>5} "
                    f"act={r790.get('active','-')} "
                    f"prep={r790.get('prepare','-')} "
                    f"cfg={r790.get('config','-')} "
                    f"st={r790.get('state','-')} "
                    f"cnt={r790.get('cnt','-'):>2} | "
                    f"792: prep={r792.get('prepared','-')} "
                    f"cruise={r792.get('cruise','-')} "
                    f"fail={r792.get('fail','-')} "
                    f"warn={r792.get('warn','-')} "
                    f"main_t={r792.get('main_t','-'):>5} "
                    f"drv_t={r792.get('drv_t','-'):>5} | "
                    f"lat={'Y' if cc.latActive else 'N'} "
                    f"v={cs.vEgo:.1f}"
                    f"{status}"
                )
                print(line)

    except KeyboardInterrupt:
        print("\n--- 停止 ---")
        print()
        print("=== 分析 ===")
        if last_792.get('fail') == 1 and last_792.get('warn') == 1:
            print("EPS 空闲状态 (TorqueFail=1, SteerWarn=1) — 这是正常的默认状态")
            print("如果 790 active=1 但 792 仍然 fail=1 warn=1:")
            print("  → EPS 没有接受转向指令")
            print("  → 检查 790 是否被 panda 拒绝 (bus 192)")
            print("  → 检查 790 格式是否正确 (Config=1, State=7)")
        if last_792.get('prepared') == 1:
            print("EPS 已准备好 (LKAS_Prepared=1) — 转向控制应该正常工作")
        if last_790.get('rejected'):
            print("*** 790 被 panda 拒绝! 检查 panda safety 配置 ***")

if __name__ == "__main__":
    main()
