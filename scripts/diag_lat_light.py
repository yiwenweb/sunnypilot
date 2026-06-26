#!/usr/bin/env python3
"""
轻量级横向状态诊断 (低干扰版)
=====================================================
与 diag_lat_full.py 不同, 本脚本:
  - 只订阅 2 个消息 (carControl, selfdriveStateSP), 不订阅 carState/carParams 等高频流
  - 使用非阻塞 update(0), 不长时间阻塞消息总线
  - 低频打印 (每 0.5s 一次), 降低对 OP 主循环的干扰

目的: 在不引发 commIssue 的前提下, 观察横向是否激活。

用法 (OP 正常运行时):
  python3 /data/openpilot/scripts/diag_lat_light.py

观察:
  latActive=Y     -> 横向已激活 (成功)
  mads.active=Y   -> MADS 已激活
  若 mads.active=Y 但 latActive=N -> 多半是 standstill/steerAtStandstill 限制
"""
import time
import cereal.messaging as messaging


def main():
    # 只订阅必要的两个低频消息, 不碰 carState/can 等高频流
    sm = messaging.SubMaster(['carControl', 'selfdriveStateSP'])

    print("轻量横向诊断 — 每 0.5s 打印一次, Ctrl+C 退出")
    print("-" * 60)

    last_print = 0.0
    try:
        while True:
            sm.update(0)          # 非阻塞, 不抢占总线
            now = time.monotonic()
            if now - last_print < 0.5:
                time.sleep(0.05)
                continue
            last_print = now

            cc = sm['carControl']
            sp = sm['selfdriveStateSP']
            mads = sp.mads

            print(
                f"latActive={'Y' if cc.latActive else 'N'} "
                f"longActive={'Y' if cc.longActive else 'N'} "
                f"enabled={'Y' if cc.enabled else 'N'} | "
                f"MADS: avail={'Y' if mads.available else 'N'} "
                f"state={mads.state} "
                f"active={'Y' if mads.active else 'N'} "
                f"enabled={'Y' if mads.enabled else 'N'}"
            )
    except KeyboardInterrupt:
        print("\n停止")


if __name__ == "__main__":
    main()
