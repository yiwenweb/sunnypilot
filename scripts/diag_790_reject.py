#!/usr/bin/env python3
"""抓取被拒绝的 790 原始数据，分析 panda 拒绝原因

用法: openpilot 运行时:
  python3 /data/openpilot/scripts/diag_790_reject.py
"""
import sys
sys.path.insert(0, '/data/openpilot')
import cereal.messaging as messaging

def decode_790_raw(dat):
    b = bytes(dat)
    if len(b) < 8:
        return f"short: {b.hex()}"
    # LKAS_Output: bits 16-26, 11-bit signed
    lkas_raw = ((b[2] | (b[3] << 8)) & 0x7FF)
    if lkas_raw > 1023:
        lkas_raw -= 2048
    # LKAS_Active: bit 28
    active = (b[3] >> 4) & 1
    # LKAS_ReqPrepare: bit 27
    req_prepare = (b[3] >> 3) & 1
    # LKAS_Config: bits 9-10
    config = (b[1] >> 1) & 3
    # LKAS_State: bits 48-50
    state = b[6] & 7
    # COUNTER: bits 52-55
    counter = (b[6] >> 4) & 0xF
    # CHECKSUM: byte 7
    checksum = b[7]
    return (f"hex={b.hex()} out={lkas_raw:>5} act={active} prep={req_prepare} "
            f"cfg={config} st={state} cnt={counter} cksum=0x{checksum:02x}")

def main():
    sm = messaging.SubMaster(['can'])
    print("=== 790 拒绝分析 ===")
    print("等待 790 消息...")

    count = 0
    seen_bus0 = 0
    seen_bus128 = 0
    seen_bus192 = 0

    # 也抓 813/814/815 看是否也被拒绝
    for _ in range(500):  # 50秒
        sm.update(100)
        if not sm.updated['can']:
            continue
        for msg in sm['can']:
            addr = msg.address
            bus = msg.src
            dat = bytes(msg.dat)

            if addr == 790:
                if bus == 0:
                    seen_bus0 += 1
                    if seen_bus0 <= 5:
                        print(f"  790 bus=0 (accepted): {decode_790_raw(dat)}")
                elif bus == 128:
                    seen_bus128 += 1
                    if seen_bus128 <= 5:
                        print(f"  790 bus=128 (returned): {decode_790_raw(dat)}")
                elif bus == 192:
                    seen_bus192 += 1
                    if seen_bus192 <= 10:
                        print(f"  790 bus=192 (REJECTED): {decode_790_raw(dat)}")

            # 检查 813/814/815 是否也被拒绝
            if addr in (813, 814, 815):
                if bus == 192:
                    print(f"  {addr} bus=192 (REJECTED): hex={dat.hex()}")
                elif bus == 0 and count < 3:
                    print(f"  {addr} bus=0 (accepted): hex={dat.hex()}")

            # 检查 944 on bus 2
            if addr == 944 and bus in (192, 2+128):
                print(f"  944 bus={bus}: hex={dat.hex()}")

        count += 1
        if count % 50 == 0:
            print(f"\n--- 统计 (第{count//10}秒) ---")
            print(f"  790: bus0={seen_bus0} bus128={seen_bus128} bus192={seen_bus192}")
            print()

    print(f"\n=== 最终统计 ===")
    print(f"790: bus0(accepted)={seen_bus0} bus128(returned)={seen_bus128} bus192(rejected)={seen_bus192}")

    if seen_bus192 > 0 and seen_bus0 == 0:
        print("\n*** 所有 790 都被拒绝! ***")
        print("可能原因:")
        print("  1. panda 固件未更新 — 需要重新编译并刷写")
        print("     bash /data/openpilot/scripts/build_panda_on_c3.sh")
        print("     python3 -c \"from panda import Panda; p=Panda(); p.flash(); p.close()\"")
        print("  2. steer_torque_cmd_checks 失败:")
        print("     - min_valid_request_frames=10: 需要连续10帧 steer_req=1 才允许非零扭矩")
        print("     - 如果 torque 在前10帧就非零，会被拒绝")
        print("     - 检查 LKAS_Active 和 LKAS_Output 的时序")
        print("  3. is_lat_active() 在 panda 内部返回 false:")
        print("     - controls_allowed_lat 未被设置")
        print("     - 检查 MADS 状态机是否正常")

if __name__ == "__main__":
    main()
