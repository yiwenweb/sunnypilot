#!/usr/bin/env python3
"""捕获 card 进程崩溃日志。
用法:
  pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
  python3 /data/openpilot/scripts/catch_card_crash.py
"""
import sys
import traceback

sys.path.insert(0, '/data/openpilot')

try:
    print("=== 启动 card ===", flush=True)
    from selfdrive.car.card import main
    main()
except SystemExit as e:
    print(f"\n=== card SystemExit: {e} ===", flush=True)
except Exception as e:
    print(f"\n=== card 崩溃 ===", flush=True)
    print(f"Exception: {type(e).__name__}: {e}", flush=True)
    traceback.print_exc()
    print("=== END ===", flush=True)
