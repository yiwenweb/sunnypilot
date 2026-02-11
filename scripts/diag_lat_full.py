#!/usr/bin/env python3
"""全面诊断 latActive 为什么是 False — 在 openpilot 运行时执行

检查整个链路:
1. Params: Mads, MadsMainCruiseAllowed, MadsUnifiedEngagementMode
2. carState: cruiseState, buttonEvents, vEgo, standstill, steerFault
3. selfdriveState: enabled, active, state
4. selfdriveStateSP: mads.available, mads.active, mads.enabled, mads.state
5. carControl: latActive, longActive, enabled
6. carParams: pcmCruise, steerAtStandstill, minSteerSpeed, alternativeExperience

用法: 在 openpilot 运行时 SSH 到 C3:
  python3 /data/openpilot/scripts/diag_lat_full.py
"""
import time
import cereal.messaging as messaging
from openpilot.common.params import Params

def main():
    params = Params()

    print("=" * 60)
    print("=== latActive 全链路诊断 ===")
    print("=" * 60)

    # 1. 检查 Params
    print("\n--- 1. Params 检查 ---")
    mads = params.get_bool("Mads")
    mads_main = params.get_bool("MadsMainCruiseAllowed")
    mads_uem = params.get_bool("MadsUnifiedEngagementMode")
    op_enabled = params.get_bool("OpenpilotEnabledToggle")
    print(f"  Mads = {mads}")
    print(f"  MadsMainCruiseAllowed = {mads_main}")
    print(f"  MadsUnifiedEngagementMode = {mads_uem}")
    print(f"  OpenpilotEnabledToggle = {op_enabled}")

    if not mads:
        print("  *** 错误: Mads=False! MADS 未启用!")
        print("  修复: python3 /data/openpilot/scripts/enable_mads.py")
    if not mads_main:
        print("  *** 警告: MadsMainCruiseAllowed=False!")
        print("  ACC 开关不会自动激活横向控制")

    # 2. 订阅消息
    print("\n--- 2. 订阅 cereal 消息 ---")
    sm = messaging.SubMaster([
        'selfdriveState', 'selfdriveStateSP',
        'carState', 'carControl', 'carParams',
        'onroadEvents', 'onroadEventsSP',
    ])

    # 等待数据
    print("等待数据...")
    for _ in range(50):
        sm.update(100)
        if sm.updated['carState']:
            break
    else:
        print("  *** 超时: 没有收到 carState 消息!")
        print("  openpilot 可能没有运行")
        return

    # 等待 carParams (每50秒发布一次，最多等60秒)
    print("等待 carParams (最多60秒)...")
    got_params = False
    for _ in range(600):
        sm.update(100)
        if sm.updated['carParams'] and sm['carParams'].brand != "":
            got_params = True
            break
    if not got_params:
        print("  *** 警告: 未收到有效 carParams，显示当前值 (可能是默认值)")

    # 3. 检查 carParams
    print("\n--- 3. CarParams ---")
    cp = sm['carParams']
    print(f"  brand = {cp.brand}")
    print(f"  carFingerprint = {cp.carFingerprint}")
    print(f"  pcmCruise = {cp.pcmCruise}")
    print(f"  openpilotLongitudinalControl = {cp.openpilotLongitudinalControl}")
    print(f"  steerAtStandstill = {cp.steerAtStandstill}")
    print(f"  minSteerSpeed = {cp.minSteerSpeed}")
    print(f"  minEnableSpeed = {cp.minEnableSpeed}")
    print(f"  alternativeExperience = {cp.alternativeExperience}")
    print(f"  ENABLE_MADS = {bool(cp.alternativeExperience & 1024)}")
    print(f"  safetyModel = {cp.safetyConfigs[0].safetyModel if cp.safetyConfigs else 'N/A'}")
    print(f"  passive = {cp.passive}")
    print(f"  notCar = {cp.notCar}")

    if not cp.steerAtStandstill:
        print("  *** 注意: steerAtStandstill=False")
        print("  停车时 latActive 会被强制为 False")

    if not (cp.alternativeExperience & 1024):
        print("  *** 错误: alternativeExperience 没有 ENABLE_MADS (1024)!")
        print("  panda 不会启用 MADS 模式")

    # 4. 实时监控
    print("\n--- 4. 实时监控 (按 Ctrl+C 停止) ---")
    print("格式: vEgo | cruise | MADS状态 | latActive | 事件")
    print("-" * 80)

    try:
        for i in range(300):  # 30秒
            sm.update(100)

            if not sm.updated['carState']:
                continue

            cs = sm['carState']
            ss = sm['selfdriveState']
            sp = sm['selfdriveStateSP']
            cc = sm['carControl']

            # MADS 状态
            mads_info = sp.mads
            mads_avail = mads_info.available
            mads_active = mads_info.active
            mads_enabled = mads_info.enabled
            mads_state = mads_info.state

            # 车辆状态
            v_ego = cs.vEgo
            standstill_speed = abs(v_ego) <= max(cp.minSteerSpeed, 0.3)
            standstill = standstill_speed or cs.standstill
            cruise_avail = cs.cruiseState.available
            cruise_en = cs.cruiseState.enabled
            steer_fault_t = cs.steerFaultTemporary
            steer_fault_p = cs.steerFaultPermanent

            # 控制状态
            lat_active = cc.latActive
            long_active = cc.longActive
            cc_enabled = cc.enabled

            # selfdriveState
            ss_enabled = ss.enabled
            ss_active = ss.active
            ss_state = ss.state

            # 计算 latActive 应该是什么
            expected_lat = (mads_active if mads_avail else ss_active)
            expected_lat = expected_lat and not steer_fault_t and not steer_fault_p
            expected_lat = expected_lat and (not standstill or cp.steerAtStandstill)

            # 按钮事件
            btn_str = ""
            for be in cs.buttonEvents:
                btn_str += f" BTN:{be.type}={'P' if be.pressed else 'R'}"

            # 事件
            events_str = ""
            for e in sm['onroadEvents']:
                events_str += f" {e.name}"

            # 输出
            line = (
                f"v={v_ego:.1f} "
                f"cruise={'ON' if cruise_avail else 'OFF'}/"
                f"{'EN' if cruise_en else 'DIS'} "
                f"MADS:{'avail' if mads_avail else 'N/A'}/"
                f"st={mads_state}/"
                f"{'ACT' if mads_active else 'inact'}/"
                f"{'en' if mads_enabled else 'dis'} "
                f"SS:st={ss_state}/{'en' if ss_enabled else 'dis'}/{'act' if ss_active else 'inact'} "
                f"lat={'Y' if lat_active else 'N'} "
                f"exp={'Y' if expected_lat else 'N'} "
                f"stall={'Y' if standstill else 'N'} "
                f"fault={steer_fault_t}/{steer_fault_p}"
            )

            if btn_str:
                line += btn_str
            if events_str:
                line += f" EVT:{events_str}"

            # 高亮关键问题
            if lat_active != expected_lat:
                line += " *** MISMATCH ***"

            print(line)

    except KeyboardInterrupt:
        print("\n--- 停止 ---")

    print("\n=== 诊断总结 ===")
    print("如果 MADS state 始终是 disabled:")
    print("  → 检查 Mads param 是否为 True")
    print("  → 检查 ACC 开关是否按下 (cruise=ON)")
    print("  → 检查 MadsMainCruiseAllowed 是否为 True")
    print("如果 MADS active=True 但 lat=N:")
    print("  → 检查 standstill (停车时需要 steerAtStandstill=True)")
    print("  → 检查 steerFault")
    print("如果 MADS available=False:")
    print("  → Mads param 未启用，运行 enable_mads.py")

if __name__ == "__main__":
    main()
