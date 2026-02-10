#!/usr/bin/env python3
"""诊断 790 REJECTED 根因 v2
必须在 D 档行驶中按 ACC 后运行！
在 openpilot 运行时执行:
  python3 /data/openpilot/scripts/diag_reject2.py
"""
import cereal.messaging as messaging

sm = messaging.SubMaster(['pandaStates', 'carParams', 'carControl',
                          'sendcan', 'can', 'selfdriveStateSP'])

print("=== 诊断 790 REJECTED v2 (D档行驶中按ACC后运行) ===")
print("等待数据...\n")

got_params = False
lat_prev = None
tx_cnt = 0
rej_cnt = 0
acc_cnt = 0

for i in range(400):
    sm.update(50)

    # panda 状态 — 每 2 秒打印一次
    if sm.updated['pandaStates'] and i % 40 == 0:
        for j, ps in enumerate(sm['pandaStates']):
            print(f"[{i:3d}] PANDA: model={ps.safetyModel} param={ps.safetyParam}"
                  f" altExp={ps.alternativeExperience}"
                  f" ctrlAllowed={ps.controlsAllowed}"
                  f" harness={ps.harnessStatus}")

    # carParams — 只打印一次
    if sm.updated['carParams'] and not got_params:
        cp = sm['carParams']
        print(f"[{i:3d}] CP: altExp={cp.alternativeExperience}"
              f" pcmCruise={cp.pcmCruise}"
              f" opLong={cp.openpilotLongitudinalControl}")
        for k, s in enumerate(cp.safetyConfigs):
            print(f"      safety[{k}]: model={s.safetyModel} param={s.safetyParam}")
        got_params = True

    # MADS 状态
    if sm.updated['selfdriveStateSP'] and i % 40 == 0:
        m = sm['selfdriveStateSP'].mads
        print(f"[{i:3d}] MADS: state={m.state} enabled={m.enabled}"
              f" active={m.active} available={m.available}")

    # latActive 变化
    if sm.updated['carControl']:
        cc = sm['carControl']
        if cc.latActive != lat_prev:
            print(f"[{i:3d}] *** latActive: {lat_prev} -> {cc.latActive} ***")
            lat_prev = cc.latActive

    # TX 790
    if sm.updated['sendcan']:
        for msg in sm['sendcan']:
            if msg.address == 790:
                tx_cnt += 1
                d = bytes(msg.dat)
                out = (d[2] | ((d[3] & 0x07) << 8))
                if out > 1023: out -= 2048
                act = (d[3] >> 4) & 1
                if tx_cnt <= 5 or tx_cnt % 20 == 0:
                    print(f"[{i:3d}] TX 790 #{tx_cnt}: Out={out:5d} Act={act} bus={msg.src}")

    # 790 回声
    if sm.updated['can']:
        for msg in sm['can']:
            if msg.address == 790:
                if msg.src == 192:
                    rej_cnt += 1
                    if rej_cnt <= 3 or rej_cnt % 20 == 0:
                        print(f"[{i:3d}] REJECTED #{rej_cnt}")
                elif msg.src == 0:
                    acc_cnt += 1
                    if acc_cnt <= 3 or acc_cnt % 20 == 0:
                        print(f"[{i:3d}] ACCEPTED #{acc_cnt}")

print(f"\nTotal: TX={tx_cnt} ACCEPTED={acc_cnt} REJECTED={rej_cnt}")
print("done")
