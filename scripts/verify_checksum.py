#!/usr/bin/env python3
"""
BYD 校验和算法验证脚本
=====================================================
目的: 抓取原厂 MPC/EPS 报文, 对每一帧分别用多种候选校验和算法计算,
      与报文实际的 byte7 对比, 自动判定哪个算法是正确的。

环境要求:
  - 车辆通电 (挂 P 即可, 不需行驶)
  - panda 直连车辆 CAN (OP 不运行, 或本脚本独占 panda)
  - 原厂 ADAS 总线必须在广播 790/792/813/814 (通电即广播)

用法:
  # 先停掉 openpilot 避免抢占 panda:
  #   pkill -f selfdrive; pkill -f pandad; sleep 3
  python3 /data/openpilot/scripts/verify_checksum.py

输出:
  每个 CAN ID 列出: 采样帧数 + 每种算法的"匹配率"。
  匹配率 100% 的算法 = 该报文的正确校验和算法。
"""
import time
from collections import defaultdict

try:
    from panda import Panda
except ImportError:
    print("ERROR: 找不到 panda 库, 请在 C3 上的 openpilot 环境运行")
    raise

# 关注的报文 (校验和都在 byte7)
TARGET_ADDRS = {
    0x316: "ACC_MPC_STATE(790)",
    0x318: "ACC_EPS_STATE(792)",
    0x32D: "ACC_HUD_ADAS(813)",
    0x32E: "ACC_CMD(814)",
    0x32F: "ACC_AEB(815)",
}

CHECKSUM_BYTE = 7  # 校验和位于第 8 个字节 (index 7)


# ---------- 候选校验和算法 ----------
# 每个函数接收 8 字节 (bytes/bytearray), 返回算出的校验和 (0-255)
# 计算时只用前 7 字节 (dat[:7]), 与 byte7 比较

def algo_nibble_af(dat):
    """当前代码使用的 nibble 算法, byte_key=0xAF"""
    d = dat[:7]
    byte_key = 0xAF
    first = sum(b >> 4 for b in d)
    second = sum(b & 0xF for b in d)
    remainder = second >> 4
    second += byte_key >> 4
    first += byte_key & 0xF
    p1 = (-first + 0x9) & 0xF
    p2 = (-second + 0x9) & 0xF
    return (((p1 + (-remainder + 5)) << 4) + p2) & 0xFF


def algo_byte_sum_inv(dat):
    """DBC 注释里写的: 0xFF - sum(dat[:7])"""
    return (0xFF - sum(dat[:7])) & 0xFF


def algo_byte_sum_2c(dat):
    """二补码: (0x100 - sum) & 0xFF  (== 256 - sum)"""
    return (0x100 - sum(dat[:7])) & 0xFF


def algo_byte_sum_plain(dat):
    """直接求和取低8位"""
    return sum(dat[:7]) & 0xFF


def algo_xor(dat):
    """所有字节异或"""
    x = 0
    for b in dat[:7]:
        x ^= b
    return x & 0xFF


# 测试多个 byte_key 的 nibble 变体, 以防 0xAF 不对
def make_nibble_variant(byte_key):
    def f(dat):
        d = dat[:7]
        first = sum(b >> 4 for b in d)
        second = sum(b & 0xF for b in d)
        remainder = second >> 4
        second += byte_key >> 4
        first += byte_key & 0xF
        p1 = (-first + 0x9) & 0xF
        p2 = (-second + 0x9) & 0xF
        return (((p1 + (-remainder + 5)) << 4) + p2) & 0xFF
    return f


ALGORITHMS = {
    "nibble_0xAF": algo_nibble_af,
    "byte_sum_inv(0xFF-sum)": algo_byte_sum_inv,
    "byte_sum_2c(0x100-sum)": algo_byte_sum_2c,
    "byte_sum_plain": algo_byte_sum_plain,
    "xor": algo_xor,
    "nibble_0x00": make_nibble_variant(0x00),
    "nibble_0xFF": make_nibble_variant(0xFF),
    "nibble_0x5A": make_nibble_variant(0x5A),
}


def main(duration=10.0):
    print("=" * 70)
    print("BYD 校验和算法验证")
    print("=" * 70)

    p = Panda()
    # safe 模式只读监听, 不主动发送; 用 silent 避免影响总线
    try:
        p.set_safety_mode(Panda.SAFETY_SILENT)
    except Exception:
        p.set_safety_mode(0)
    time.sleep(0.3)
    p.can_clear(0xFFFF)

    # 每个 (addr,bus): 每种算法的匹配计数, 总采样数, 样例帧
    match_count = defaultdict(lambda: defaultdict(int))
    total_count = defaultdict(int)
    samples = {}

    print(f"\n采集 {duration:.0f} 秒... (确保车辆通电, ADAS 总线在广播)\n")
    start = time.time()
    while time.time() - start < duration:
        msgs = p.can_recv()
        for msg in msgs:
            if len(msg) == 4:
                addr, _, dat, bus = msg
            elif len(msg) == 3:
                addr, dat, bus = msg
            else:
                continue
            if addr not in TARGET_ADDRS:
                continue
            if len(dat) < 8:
                continue

            key = (addr, bus)
            total_count[key] += 1
            if key not in samples:
                samples[key] = bytes(dat).hex()

            actual = dat[CHECKSUM_BYTE]
            for name, fn in ALGORITHMS.items():
                try:
                    if fn(dat) == actual:
                        match_count[key][name] += 1
                except Exception:
                    pass
        time.sleep(0.002)

    p.close()

    # ---------- 输出结果 ----------
    if not total_count:
        print("!!! 未收到任何目标报文 !!!")
        print("排查: 1) 车辆是否通电  2) panda 是否接对 CAN(ADAS)总线")
        print("      3) openpilot/pandad 是否仍占用 panda(需先 pkill)")
        return

    for key in sorted(total_count.keys()):
        addr, bus = key
        n = total_count[key]
        print(f"\n### {TARGET_ADDRS[addr]}  bus={bus}  采样={n} 帧")
        print(f"    样例: {samples[key]}")
        results = []
        for name in ALGORITHMS:
            c = match_count[key].get(name, 0)
            rate = 100.0 * c / n if n else 0
            results.append((rate, name, c))
        results.sort(reverse=True)
        for rate, name, c in results:
            flag = "  <== 匹配!" if rate >= 99.9 else ""
            print(f"      {name:28s}: {rate:6.1f}%  ({c}/{n}){flag}")

    print("\n" + "=" * 70)
    print("判读: 匹配率 100% 的算法即为该报文的正确校验和算法。")
    print("如果没有任何算法达到 100%, 说明校验和可能:")
    print("  - 不在 byte7 (改 CHECKSUM_BYTE 试别的位置)")
    print("  - 覆盖范围不是 dat[:7] (可能含/不含某些字节)")
    print("  - 是其他算法 (需要进一步逆向)")
    print("=" * 70)


if __name__ == "__main__":
    import sys
    dur = float(sys.argv[1]) if len(sys.argv) > 1 else 10.0
    main(dur)
