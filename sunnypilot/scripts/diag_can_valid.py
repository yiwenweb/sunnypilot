#!/usr/bin/env python3
"""
诊断 canValid 问题 — 监控所有 CAN parser 消息的状态
在 C3 上运行: python3 /data/openpilot/scripts/diag_can_valid.py

这个脚本直接监控 CAN 总线上的消息到达情况，
帮助找出哪个消息超时导致 canValid=False。
"""
import time
import cereal.messaging as messaging

# BYD CAN parser 注册的所有消息 (Bus 0)
MONITORED_MESSAGES = {
    287: "EPS",           # freq=0 (auto-learn)
    289: "CARSPEED",      # freq=0 (auto-learn)
    578: "DRIVE_STATE",   # freq=20Hz, timeout=500ms
    834: "PEDAL",         # freq=20Hz, timeout=500ms
    546: "YAW_RATE",      # freq=20Hz, timeout=500ms
    547: "AXAY",          # freq=20Hz, timeout=500ms
    301: "BCM",           # freq=1Hz, timeout=10s
    307: "STALKS",        # freq=1Hz, timeout=10s
    85:  "EPB",           # freq=0 (auto-learn)
    944: "PCM_BUTTONS",   # freq=0 (auto-learn)
    792: "ACC_EPS_STATE", # freq=nan (ignore_alive)
}

# openpilot TX 消息 (不应出现在 Bus 0 RX 中，但可能被转发回来)
TX_MESSAGES = {
    790: "ACC_MPC_STATE (TX)",
    813: "ACC_HUD_ADAS (TX)",
    814: "ACC_CMD (TX)",
    815: "ACC_AEB (TX)",
}

def main():
    sm = messaging.SubMaster(['carState', 'selfdriveState', 'can'])

    last_seen = {}
    msg_count = {}
    for addr in list(MONITORED_MESSAGES.keys()) + list(TX_MESSAGES.keys()):
        last_seen[addr] = {0: 0.0, 2: 0.0}  # per bus
        msg_count[addr] = {0: 0, 2: 0}

    start_time = time.monotonic()
    last_print = 0.0

    print("=" * 75)
    print("BYD CAN 消息监控 — 诊断 canValid 问题")
    print("开 ACC 并等速度 > 1km/h 后观察哪个消息消失或延迟")
    print("=" * 75)

    while True:
        sm.update(100)
        now = time.monotonic()

        if sm.updated['can']:
            for msg in sm['can']:
                if msg.address in last_seen and msg.src in (0, 2):
                    last_seen[msg.address][msg.src] = now
                    msg_count[msg.address][msg.src] += 1

        # 每 0.5 秒打印
        if now - last_print < 0.5:
            continue
        last_print = now
        elapsed = now - start_time

        cs = sm['carState']
        ss = sm['selfdriveState']
        can_valid = cs.canValid if sm.recv_frame['carState'] > 0 else "N/A"
        enabled = ss.enabled if sm.recv_frame['selfdriveState'] > 0 else "N/A"
        active = ss.active if sm.recv_frame['selfdriveState'] > 0 else "N/A"
        alert = ss.alertText1 if sm.recv_frame['selfdriveState'] > 0 else ""

        print(f"\n[{elapsed:.1f}s] canValid={can_valid} enabled={enabled} active={active}")
        if alert:
            print(f"  ALERT: {alert}")

        print(f"{'Addr':>6} {'Name':<22} {'Bus0_cnt':>8} {'Bus0_gap':>9} {'Bus2_cnt':>8} {'Bus2_gap':>9} {'Status'}")
        print("-" * 80)

        all_msgs = {**MONITORED_MESSAGES, **TX_MESSAGES}
        for addr in sorted(all_msgs.keys()):
            name = all_msgs[addr]
            c0 = msg_count[addr][0]
            c2 = msg_count[addr][2]
            ls0 = last_seen[addr][0]
            ls2 = last_seen[addr][2]

            gap0 = f"{(now - ls0)*1000:.0f}ms" if ls0 > 0 else "never"
            gap2 = f"{(now - ls2)*1000:.0f}ms" if ls2 > 0 else "never"

            # 判断状态
            if addr == 792:
                status = "(ignore_alive)"
            elif addr in TX_MESSAGES:
                status = ""
            elif ls0 == 0:
                status = "❌ NEVER SEEN"
            elif (now - ls0) > 2.0:
                status = "⚠️  TIMEOUT!"
            elif (now - ls0) > 0.5:
                status = "⚠️  SLOW"
            else:
                status = "OK"

            print(f"{addr:>6} {name:<22} {c0:>8} {gap0:>9} {c2:>8} {gap2:>9} {status}")

if __name__ == "__main__":
    main()
