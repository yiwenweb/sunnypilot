#!/usr/bin/env python3
"""捕获 card 进程崩溃日志 v2。
在 openpilot 正常运行时，杀掉 card 让 manager 重启，
然后 attach 到新 card 进程的 stderr 来捕获崩溃。

用法（openpilot 正常运行时）:
  python3 /data/openpilot/scripts/catch_card_crash.py

或者停止 openpilot 后独立运行:
  pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
  python3 /data/openpilot/scripts/catch_card_crash.py
"""
import sys
import os
import traceback
import time

sys.path.insert(0, '/data/openpilot')
os.environ.setdefault('BASEDIR', '/data/openpilot')

# Monkey-patch card.py 的 step 方法来捕获异常
print("=== Card Crash Catcher v2 ===", flush=True)

try:
    from selfdrive.car.card import Car, main
    from openpilot.common.realtime import config_realtime_process, Priority

    # 先处理 realtime 配置
    try:
        config_realtime_process(4, Priority.CTRL_HIGH)
    except Exception as e:
        print(f"realtime config error (ignored): {e}", flush=True)

    car = Car()

    # Wrap step method
    original_step = car.step
    step_count = 0

    def wrapped_step():
        global step_count
        step_count += 1
        try:
            original_step()
        except Exception as e:
            print(f"\n=== CRASH at step {step_count} ===", flush=True)
            print(f"Exception: {type(e).__name__}: {e}", flush=True)
            traceback.print_exc()
            # 打印当前状态
            try:
                cs = car.CS
                print(f"\n--- CarState ---", flush=True)
                print(f"  vEgo={cs.vEgo:.1f} latActive={getattr(car, 'last_actuators_output', 'N/A')}", flush=True)
                print(f"  lkas_prepared={cs.lkas_prepared}", flush=True)
                print(f"  steer_torque_driver={cs.steer_torque_driver}", flush=True)
            except Exception:
                pass
            raise

    car.step = wrapped_step

    print("启动 card_thread (等待崩溃)...", flush=True)
    car.card_thread()

except SystemExit as e:
    print(f"\n=== SystemExit: {e} ===", flush=True)
except Exception as e:
    print(f"\n=== 崩溃 ===", flush=True)
    print(f"Exception: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    print("=== END ===", flush=True)
