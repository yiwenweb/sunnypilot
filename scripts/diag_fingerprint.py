#!/usr/bin/env python3
"""诊断 fingerprint 是否正确加载

直接从 Params 读取 CarParams 和 CarPlatformBundle，
不依赖 cereal 消息的发布周期。

用法: SSH 到 C3:
  python3 /data/openpilot/scripts/diag_fingerprint.py
"""
import sys
sys.path.insert(0, '/data/openpilot')

from cereal import car
from openpilot.common.params import Params

def main():
    params = Params()

    print("=" * 60)
    print("=== Fingerprint 诊断 ===")
    print("=" * 60)

    # 1. CarPlatformBundle
    print("\n--- 1. CarPlatformBundle ---")
    try:
        bundle = params.get("CarPlatformBundle")
        print(f"  raw = {bundle}")
        if bundle:
            platform = bundle.get("platform", None)
            brand = bundle.get("brand", None)
            print(f"  platform = {platform}")
            print(f"  brand = {brand}")
        else:
            print("  *** CarPlatformBundle 为空!")
    except Exception as e:
        print(f"  *** 读取失败: {e}")

    # 2. CarParams (从缓存读取)
    print("\n--- 2. CarParams (从 Params 缓存) ---")
    for key in ["CarParams", "CarParamsCache", "CarParamsPersistent"]:
        try:
            raw = params.get(key)
            if raw is not None:
                with car.CarParams.from_bytes(raw) as cp:
                    print(f"  [{key}]")
                    print(f"    brand = '{cp.brand}'")
                    print(f"    carFingerprint = '{cp.carFingerprint}'")
                    print(f"    safetyModel = {cp.safetyConfigs[0].safetyModel if cp.safetyConfigs else 'N/A'}")
                    print(f"    steerAtStandstill = {cp.steerAtStandstill}")
                    print(f"    alternativeExperience = {cp.alternativeExperience}")
                    print(f"    pcmCruise = {cp.pcmCruise}")
                    print(f"    passive = {cp.passive}")
                    print(f"    openpilotLongitudinalControl = {cp.openpilotLongitudinalControl}")
                    print(f"    fingerprintSource = {cp.fingerprintSource}")
            else:
                print(f"  [{key}] = None (不存在)")
        except Exception as e:
            print(f"  [{key}] 读取失败: {e}")

    # 3. 检查 interfaces 是否包含 BYD
    print("\n--- 3. interfaces 检查 ---")
    try:
        from opendbc.car.car_helpers import interfaces
        byd_key = "BYD_TANG_DM_2018"
        if byd_key in interfaces:
            print(f"  interfaces['{byd_key}'] = {interfaces[byd_key]}")
            print("  ✓ BYD 已注册在 interfaces 中")
        else:
            print(f"  *** '{byd_key}' 不在 interfaces 中!")
            print(f"  可用的 keys (前20个): {list(interfaces.keys())[:20]}")
    except Exception as e:
        print(f"  *** 导入失败: {e}")

    # 4. 检查 FINGERPRINTS 是否包含 BYD
    print("\n--- 4. FINGERPRINTS 检查 ---")
    try:
        from opendbc.car.fingerprints import _FINGERPRINTS
        found = False
        for k in _FINGERPRINTS:
            if "BYD" in str(k).upper() or "TANG" in str(k).upper():
                fp = _FINGERPRINTS[k]
                ids = sorted(fp[0].keys()) if fp else []
                print(f"  {k}: {len(ids)} IDs")
                print(f"    IDs: {ids}")
                found = True
        if not found:
            print("  *** 没有找到 BYD 相关的 fingerprint!")
            print(f"  所有 keys: {[str(k) for k in _FINGERPRINTS.keys()][:10]}")
    except Exception as e:
        print(f"  *** 导入失败: {e}")

    # 5. 检查 selfdrive 日志
    print("\n--- 5. 建议 ---")
    print("  查看 card.py 日志:")
    print("    journalctl --no-pager -u selfdrive -n 100 | grep -i 'finger\\|byd\\|brand\\|candidate\\|MOCK'")
    print("  查看完整启动日志:")
    print("    journalctl --no-pager -u selfdrive -n 200 | head -50")

if __name__ == "__main__":
    main()
