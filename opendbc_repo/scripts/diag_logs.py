#!/usr/bin/env python3
"""
BYD 诊断日志工具

实时监控 openpilot 关键状态，帮助排查：
- CAN Error / canValid 状态
- 车辆仪表报错原因（MPC/雷达报错）
- panda safety 状态（controls_allowed, fwd_hook 行为）
- 消息收发情况

使用方法:
  ssh comma@<C3_IP>
  cd /data/openpilot
  python3 opendbc_repo/scripts/diag_logs.py

操作说明:
  1. 启动后观察输出
  2. 按 ACC 按钮，观察状态变化
  3. 按 Ctrl+C 结束
"""

import time
import cereal.messaging as messaging

def main():
    sm = messaging.SubMaster([
        'carState', 'carControl', 'carOutput', 'controlsState',
        'pandaStates', 'selfdriveState', 'onroadEvents', 'radarState',
        'can',
    ])

    print("=" * 80)
    print("BYD 诊断日志 - 实时监控")
    print("按 ACC 按钮观察状态变化，Ctrl+C 结束")
    print("=" * 80)

    frame = 0
    last_print = 0

    # 统计 Bus 0/2 上 790/792/813/814/815 的收发
    msg_counts = {}
    last_counts = {}

    try:
        while True:
            sm.update(100)
            now = time.monotonic()
            frame += 1

            # 统计 CAN 消息
            if sm.updated['can']:
                for msg in sm['can']:
                    key = (msg.address, msg.src)
                    if key not in msg_counts:
                        msg_counts[key] = 0
                    msg_counts[key] += 1

            # 每 2 秒打印一次
            if now - last_print < 2.0:
                continue
            last_print = now

            print(f"\n{'='*80}")
            print(f"Frame {frame} | {time.strftime('%H:%M:%S')}")
            print(f"{'='*80}")

            # === 1. CarState 关键状态 ===
            if sm.updated['carState'] or sm.valid['carState']:
                cs = sm['carState']
                print(f"\n[CarState]")
                print(f"  canValid={cs.canValid} canTimeout={cs.canTimeout}")
                print(f"  vEgo={cs.vEgo:.1f}m/s standstill={cs.standstill}")
                print(f"  steerAngle={cs.steeringAngleDeg:.1f}° steerTorque={cs.steeringTorque:.0f}")
                print(f"  steerPressed={cs.steeringPressed} steerFaultTemp={cs.steerFaultTemporary} steerFaultPerm={cs.steerFaultPermanent}")
                print(f"  gasPressed={cs.gasPressed} brakePressed={cs.brakePressed}")
                print(f"  gear={cs.gearShifter} parkBrake={cs.parkingBrake}")
                print(f"  leftBlinker={cs.leftBlinker} rightBlinker={cs.rightBlinker}")
                print(f"  doorOpen={cs.doorOpen} seatbeltUnlatched={cs.seatbeltUnlatched}")
                print(f"  yawRate={cs.yawRate:.4f} rad/s")
                print(f"  cruiseState: avail={cs.cruiseState.available} enabled={cs.cruiseState.enabled} speed={cs.cruiseState.speed:.1f}")
                if cs.buttonEvents:
                    for be in cs.buttonEvents:
                        print(f"  BUTTON: type={be.type} pressed={be.pressed}")

            # === 2. SelfdriveState ===
            if sm.valid['selfdriveState']:
                ss = sm['selfdriveState']
                print(f"\n[SelfdriveState]")
                print(f"  state={ss.state} enabled={ss.enabled} active={ss.active}")
                print(f"  engageable={ss.engageable}")
                if ss.alertText1 or ss.alertText2:
                    print(f"  ALERT: {ss.alertText1} | {ss.alertText2}")
                    print(f"  alertType={ss.alertType} alertStatus={ss.alertStatus}")

            # === 3. Panda 状态 ===
            if sm.valid['pandaStates']:
                for i, ps in enumerate(sm['pandaStates']):
                    print(f"\n[Panda {i}]")
                    print(f"  safetyModel={ps.safetyModel} safetyParam={ps.safetyParam}")
                    print(f"  controlsAllowed={ps.controlsAllowed}")
                    print(f"  rxChecksInvalid={ps.safetyRxChecksInvalid}")
                    if ps.faults:
                        print(f"  FAULTS: {list(ps.faults)}")

            # === 4. OnroadEvents ===
            if sm.updated['onroadEvents']:
                events = sm['onroadEvents']
                if events:
                    print(f"\n[OnroadEvents]")
                    for e in events:
                        print(f"  {e.name} (noEntry={e.noEntry} softDisable={e.softDisable} immediateDisable={e.immediateDisable})")

            # === 5. Radar 状态 ===
            if sm.valid['radarState']:
                rs = sm['radarState']
                errs = rs.radarErrors
                if any(errs.to_dict().values()):
                    print(f"\n[RadarState] ERRORS: {errs.to_dict()}")

            # === 6. 关键消息收发统计 ===
            print(f"\n[CAN 消息统计] (累计)")
            targets = [
                (790, "ACC_MPC_STATE"), (792, "ACC_EPS_STATE"),
                (813, "ACC_HUD_ADAS"), (814, "ACC_CMD"), (815, "ACC_AEB"),
                (944, "PCM_BUTTONS"),
                (301, "BCM"), (307, "STALKS"), (546, "YAW_RATE"), (547, "AXAY"),
            ]
            for addr, name in targets:
                counts_str = []
                for bus in [0, 2, 128, 130]:
                    key = (addr, bus)
                    cnt = msg_counts.get(key, 0)
                    prev = last_counts.get(key, 0)
                    rate = (cnt - prev) / 2.0  # 2秒间隔
                    if cnt > 0:
                        counts_str.append(f"Bus{bus}={cnt}({rate:.0f}/s)")
                if counts_str:
                    print(f"  {name:>18}({addr}): {', '.join(counts_str)}")
                else:
                    print(f"  {name:>18}({addr}): 无数据")

            last_counts = dict(msg_counts)

    except KeyboardInterrupt:
        print("\n\n诊断结束。请把以上输出截图发给开发者。")


if __name__ == "__main__":
    main()
