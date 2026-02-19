#!/usr/bin/env python3
"""
诊断脚本: 在 openpilot 运行时检查 pandaStates
用法: python3 /data/openpilot/scripts/diag_panda_live.py

检查项:
1. safety_mode 是否为 35 (BYD)
2. alternativeExperience 是否包含 1024 (ENABLE_MADS)
3. controlsAllowed 是否为 1
4. safetyTxBlocked 计数
5. safetyRxChecksInvalid 是否为 0
"""
import time
from cereal import messaging

sm = messaging.SubMaster(['pandaStates', 'carState', 'controlsState'])

print("等待 openpilot 数据... (确保 openpilot 正在运行)")
print("按 Ctrl+C 退出\n")

for i in range(30):
    sm.update(2000)
    
    if sm.updated['pandaStates']:
        for j, ps in enumerate(sm['pandaStates']):
            alt_exp = ps.alternativeExperience
            has_mads = bool(alt_exp & 1024)
            print(f"[{i:2d}] panda{j}: safety={ps.safetyModel} param={ps.safetyParam} "
                  f"altExp={alt_exp}(MADS={'YES' if has_mads else 'NO'}) "
                  f"ctrl={ps.controlsAllowed} txBlk={ps.safetyTxBlocked} "
                  f"rxInv={ps.safetyRxChecksInvalid}")
    
    if sm.updated['controlsState']:
        cs = sm['controlsState']
        try:
            print(f"       controls: active={cs.active} latActive={cs.lateralActive} "
                  f"state={cs.state}")
        except Exception:
            print(f"       controls: state={cs.state}")
    
    if sm.updated['carState']:
        car = sm['carState']
        print(f"       car: steerTorqueEps={car.steeringTorqueEps:.0f} "
              f"steerTorque={car.steeringTorque:.0f} "
              f"cruiseAvail={car.cruiseState.available} "
              f"cruiseEnabled={car.cruiseState.enabled}")
    
    print()
    time.sleep(1)
