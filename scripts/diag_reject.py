#!/usr/bin/env python3
"""诊断 790 REJECTED 根因 — 在 openpilot 运行时执行
检查:
1. panda 的 alternativeExperience 是否包含 ENABLE_MADS (1024)
2. panda 的 controls_allowed / controls_allowed_lat
3. 790 发送时的 torque 和 steer_req 值
4. 时序: latActive 变化 vs 790 发送 vs REJECTED

用法: 在 C3 上 openpilot 运行时执行:
  python3 /data/openpilot/scripts/diag_reject.py
"""
import cereal.messaging as messaging
import time

sm = messaging.SubMaster(['pandaStates', 'carParams', 'carControl', 'carOutput',
                          'sendcan', 'can', 'selfdriveStateSP', 'selfdriveState'])

print("=== 诊断 790 REJECTED 根因 ===")
print("等待数据...")

lat_active_prev = None
got_params = False

for i in range(300):
    sm.update(100)

    # 1. 检查 panda 状态
    if sm.updated['pandaStates'] and i % 30 == 0:
        for j, ps in enumerate(sm['pandaStates']):
            print(f"\n[{i:3d}] PANDA[{j}]:")
            print(f"  safetyModel={ps.safetyModel} safetyParam={ps.safetyParam}")
            print(f"  alternativeExperience={ps.alternativeExperience} (MADS={ps.alternativeExperience & 1024 != 0})")
            print(f"  controlsAllowed={ps.controlsAllowed}")
            print(f"  harnessStatus={ps.harnessStatus}")

    # 2. 检查 carParams (只打印一次)
    if sm.updated['carParams'] and not got_params:
        cp = sm['carParams']
        print(f"\n[{i:3d}] CAR PARAMS:")
        print(f"  alternativeExperience={cp.alternativeExperience} (MADS={cp.alternativeExperience & 1024 != 0})")
        print(f"  pcmCruise={cp.pcmCruise}")
        print(f"  openpilotLongitudinalControl={cp.openpilotLongitudinalControl}")
        sc = cp.safetyConfigs
        for k, s in enumerate(sc):
            print(f"  safetyConfig[{k}]: model={s.safetyModel} param={s.safetyParam}")
        got_params = True

    # 3. 检查 selfdriveState
    if sm.updated['selfdriveState'] and i % 30 == 0:
        ss = sm['selfdriveState']
        print(f"[{i:3d}] selfdriveState: enabled={ss.enabled} active={ss.active}")

    # 4. 检查 MADS 状态
    if sm.updated['selfdriveStateSP'] and i % 30 == 0:
        sp = sm['selfdriveStateSP']
        mads = sp.mads
        print(f"[{i:3d}] MADS: state={mads.state} enabled={mads.enabled} active={mads.active} available={mads.available}")

    # 5. 检查 latActive 变化
    if sm.updated['carControl']:
        cc = sm['carControl']
        lat_active = cc.latActive
        if lat_active != lat_active_prev:
            print(f"\n[{i:3d}] *** latActive changed: {lat_active_prev} -> {lat_active} ***")
            lat_active_prev = lat_active

    # 6. 检查 sendcan 中的 790
    if sm.updated['sendcan']:
        for msg in sm['sendcan']:
            if msg.address == 790:
                d = bytes(msg.dat)
                lkas_out = (d[2] | ((d[3] & 0x07) << 8))
                if lkas_out > 1023: lkas_out -= 2048
                req_prep = (d[3] >> 3) & 1
                lkas_act = (d[3] >> 4) & 1
                if i % 10 == 0:
                    print(f"[{i:3d}] TX 790: Out={lkas_out:5d} Prep={req_prep} Act={lkas_act} bus={msg.src}")

    # 7. 检查 can 中的 790 回声
    if sm.updated['can']:
        for msg in sm['can']:
            if msg.address == 790:
                bus = msg.src
                if bus == 192:
                    d = bytes(msg.dat)
                    lkas_out = (d[2] | ((d[3] & 0x07) << 8))
                    if lkas_out > 1023: lkas_out -= 2048
                    req_prep = (d[3] >> 3) & 1
                    lkas_act = (d[3] >> 4) & 1
                    if i % 10 == 0:
                        print(f"[{i:3d}] REJECTED 790: Out={lkas_out:5d} Prep={req_prep} Act={lkas_act}")
                elif bus == 0:
                    if i % 30 == 0:
                        print(f"[{i:3d}] ACCEPTED 790 on bus 0")

print("\ndone")
