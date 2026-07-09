#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C3 端驾驶统计计算脚本。

功能：
  - 扫描 /data/media/0/realdata/ 下所有 segment
  - 解析每个 segment 的 qlog.zst，提取里程、时长、事件
  - 按日期聚合输出 JSON，供 Android App 数据中台导入

用法（在 C3 上）：
    cd /data/openpilot
    python3 c3_scripts/calc_drive_stats.py

输出（stdout，JSON 数组）：
    [{
      "date": "2026-07-08",
      "totalDistanceKm": 45.2,
      "assistedDistanceKm": 38.1,
      "manualDistanceKm": 7.1,
      "durationMinutes": 62,
      "assistedDurationMinutes": 51,
      "maxSpeedKmh": 112.3,
      "takeovers": 3,
      "collisionWarning": 0,
      "tailgating": 2,
      "leadCarStationary": 4,
      "leadCarEmergencyBrake": 1,
      "leadCarSlow": 5,
      "startReminder": 0,
      "laneChangeAssist": 12,
      "safetyScore": 92
    }, ...]
"""

import sys
import os
import json
import glob
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "/data/openpilot")

try:
    from tools.lib.logreader import LogReader
except Exception as e:
    print("无法导入 LogReader，请确认在 /data/openpilot 下运行", file=sys.stderr)
    print(f"错误: {e}", file=sys.stderr)
    sys.exit(1)

REALDATA = "/data/media/0/realdata"
QLOG_NAMES = ("qlog.zst", "qlog.bz2", "qlog")

# 跟车/前车判定阈值
TAILGATE_DIST_M = 8.0        # 跟车距离 < 8m 视为过近
TAILGATE_MIN_EGO_MS = 3.0    # 自身车速需 > 3m/s
LEAD_STATIONARY_MS = 0.5     # 前车速度 < 0.5m/s 视为静止
LEAD_SLOW_MS = 3.0           # 前车速度 < 3m/s 视为龟速
LEAD_SLOW_GAP_MS = 1.0       # 且自身比前车快 > 1m/s

# ---------------------------------------------------------------------------
# Event name → DriveStats field mapping
# (Enum strings from cereal/log.capnp EventName)
# ---------------------------------------------------------------------------
EVENT_MAP = {
    "fcw":                "collisionWarning",
    "stockFcw":           "collisionWarning",
    "aeb":                "leadCarEmergencyBrake",
    "stockAeb":           "leadCarEmergencyBrake",
    "laneChange":         "laneChangeAssist",
    "preLaneChangeLeft":  "laneChangeAssist",
    "preLaneChangeRight": "laneChangeAssist",
    "startup":            "startReminder",
}

# 接管次数由 SegmentAccum.record_engaged_transition() 计算，
# 仅当 engaged 连续持续 ≥2 秒后 disengage 才计数一次接管，
# 以此过滤 ACC 临时断开等噪声。不再使用 pedalPressed 等每帧刷新的事件。

# 需要从 radarState lead 推导的指标
LEAD_EVENTS = {"tailgating", "leadCarStationary", "leadCarSlow"}


# ---------------------------------------------------------------------------
# Per-segment accumulator
# ---------------------------------------------------------------------------
class SegmentAccum:
    __slots__ = ("total_m", "assisted_m", "assisted_duration_s", "max_v_ego", "driving_time_s",
                 "start_ns", "last_ns", "events", "edge_state", "segment_date",
                 "takeover_count", "_last_engaged", "_last_ts", "_engage_ts")

    def __init__(self, date_str):
        self.segment_date = date_str
        self.total_m = 0.0
        self.assisted_m = 0.0
        self.assisted_duration_s = 0.0
        self.max_v_ego = 0.0
        self.driving_time_s = 0.0    # 实际积分累计时长（代替 logMonoTime 跨度）
        self.start_ns = None
        self.last_ns = None
        self.events = {}          # event_name → count (rising-edge)
        self.edge_state = {}      # event_name → last active bool
        self.takeover_count = 0   # 真实接管：engaged 持续 ≥2s 后 disengage 才计数
        self._last_engaged = None
        self._last_ts = None
        self._engage_ts = None    # 最近一次 engagement 开始的 ts_ns

    def integrate(self, v_ego, engaged, ts_ns):
        """Integrate distance from vEgo (m/s) × dt — called once per carState frame."""
        if self.start_ns is None:
            self.start_ns = ts_ns
            self.last_ns = ts_ns
            return

        dt_s = (ts_ns - self.last_ns) * 1e-9
        if dt_s <= 0 or dt_s > 5.0:
            # Clamp: skip absurd gaps (>5 sec = likely ignition cycle boundary)
            self.last_ns = ts_ns
            return

        ds_m = v_ego * dt_s
        self.driving_time_s += dt_s    # 实际行驶秒数
        self.total_m += ds_m
        if engaged:
            self.assisted_m += ds_m
            self.assisted_duration_s += dt_s
        if v_ego > self.max_v_ego:
            self.max_v_ego = v_ego

        self.last_ns = ts_ns

    def register_edge(self, key, active):
        """Count only on rising edge (active: False→True).

        onroadEvents / lead status persist across many frames, so without
        edge detection a single event would be counted dozens of times.
        """
        was = self.edge_state.get(key, False)
        if active and not was:
            self.events[key] = self.events.get(key, 0) + 1
        self.edge_state[key] = active

    def record_engaged_transition(self, engaged, ts_ns):
        """Count a takeover only when engaged was continuously true for ≥2 s.

        'logMonoTime' is boot time (not wall clock), but within a single
        segment the monotonic span is proportional to real time.  This 2 s
        hysteresis filters out noise / brief ACC disengagements that are
        not actual driver takeovers.
        """
        if self._last_ts != ts_ns:
            if engaged and (self._last_engaged is None or not self._last_engaged):
                self._engage_ts = ts_ns         # rising edge → note when engagement started
            elif not engaged and self._last_engaged:
                elapsed = (ts_ns - self._engage_ts) * 1e-9 if self._engage_ts is not None else 0.0
                if elapsed >= 2.0:              # only count if engaged lasted ≥ 2 s
                    self.takeover_count += 1
            self._last_engaged = engaged
            self._last_ts = ts_ns

    def register_event(self, event_name):
        self.events[event_name] = self.events.get(event_name, 0) + 1

    def duration_min(self):
        """驾驶时长 = 实际积分累计的秒数（不靠 logMonoTime 跨度）。"""
        return int(self.driving_time_s / 60)

    def to_daily_drive_stats(self):
        """Convert segment accumulator to a per-day stats dict (additive)."""
        manual_m = max(0.0, self.total_m - self.assisted_m)

        # 接管次数 = engaged 持续 ≥2s 后 disengage 才算一次（见 record_engaged_transition）
        takeover_count = self.takeover_count

        # Count other event types
        col_warn = self.events.get("fcw", 0) + self.events.get("stockFcw", 0)
        aeb_cnt = self.events.get("aeb", 0) + self.events.get("stockAeb", 0)
        lc_cnt = (self.events.get("laneChange", 0) +
                  self.events.get("preLaneChangeLeft", 0) +
                  self.events.get("preLaneChangeRight", 0))
        startup_cnt = self.events.get("startup", 0)

        return {
            "date": self.segment_date,
            "totalDistanceKm": round(self.total_m / 1000.0, 1),
            "assistedDistanceKm": round(self.assisted_m / 1000.0, 1),
            "manualDistanceKm": round(manual_m / 1000.0, 1),
            "durationMinutes": self.duration_min(),
            "assistedDurationMinutes": int(self.assisted_duration_s / 60),
            "maxSpeedKmh": round(self.max_v_ego * 3.6, 1),
            "takeovers": takeover_count,
            "collisionWarning": col_warn,
            "tailgating": self.events.get("tailgating", 0),
            "leadCarStationary": self.events.get("leadCarStationary", 0),
            "leadCarEmergencyBrake": aeb_cnt,
            "leadCarSlow": self.events.get("leadCarSlow", 0),
            "startReminder": startup_cnt,
            "laneChangeAssist": lc_cnt,
            "maxSegmentDistanceKm": round(self.total_m / 1000.0, 1),
            "longestSegmentMinutes": self.duration_min(),
            "safetyScore": 0,            # computed later in aggregation
        }


def find_qlog(seg_dir):
    for name in QLOG_NAMES:
        p = os.path.join(seg_dir, name)
        if os.path.isfile(p):
            return p
    return None


def _read_date_from_qlog(qlog):
    """读取 qlog 中真正的录制日期。

    logMonoTime 是开机以来的纳秒数(boot time)，不是 Unix 时间，
    所以不能直接用它算日期。正确做法：
      1. 找 clocksState.wallTimeNanos（设备墙钟时间）
      2. 找 gpsLocationExternal.timestamp（GPS 时间）
      3. 都找不到时回退到文件的 mtime（至少接近录制日期）
    前两条最多扫描前 5000 条消息避免太慢。
    """
    try:
        lr = LogReader(qlog)
        for i, msg in enumerate(lr):
            if i >= 5000:
                break
            w = msg.which()
            ts_ns = None
            if w == "clocksState":
                cs = msg.clocksState
                if hasattr(cs, "wallTimeNanos"):
                    ts_ns = cs.wallTimeNanos
            elif w == "gpsLocationExternal":
                gps = msg.gpsLocationExternal
                if hasattr(gps, "timestamp"):
                    ts_ns = int(gps.timestamp * 1e9)
            if ts_ns is not None and ts_ns >= 1262304000_000_000_000:
                return datetime.fromtimestamp(ts_ns / 1e9, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass

    # 最后回退：文件修改时间（大部份备份会保留 mtime）
    try:
        mtime = os.path.getmtime(qlog)
        if mtime >= 1262304000:      # 2010-01-01
            return datetime.fromtimestamp(mtime, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def parse_segment_date(seg_dir):
    """返回 segment 的日期字符串(YYYY-MM-DD)，或 None。

    优先级：
      1. 文件夹名里的起始时间戳 <start_ts>--<route>--<idx>。
         仅当它像真实的 Unix 时间戳(>= 2010 年)时才采用。
      2. 兜底：从 qlog 内容读墙钟时间（clocksState / gpsLocation）。
      3. 最后回退到文件修改时间。
    """
    seg_name = os.path.basename(seg_dir)
    try:
        ts_str = seg_name.split("--")[0]
        ts = None
        for base in (10, 16):
            try:
                ts = int(ts_str, base)
                break
            except ValueError:
                continue
        if ts is not None and ts >= 1262304000:   # 2010-01-01
            return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    except (ValueError, IndexError, OSError):
        pass

    qlog = find_qlog(seg_dir)
    if qlog is not None:
        return _read_date_from_qlog(qlog)
    return None


def _lead_active(lead, v_ego):
    """Return (tailgate, stationary, slow) booleans for one lead."""
    if lead is None:
        return False, False, False
    status = getattr(lead, "status", False)
    if not status:
        return False, False, False
    d_rel = getattr(lead, "dRel", 1e9)
    v_lead = getattr(lead, "vLead", 0.0)

    tailgate = d_rel < TAILGATE_DIST_M and v_ego > TAILGATE_MIN_EGO_MS
    stationary = v_lead < LEAD_STATIONARY_MS
    slow = v_lead < LEAD_SLOW_MS and v_ego > v_lead + LEAD_SLOW_GAP_MS
    return tailgate, stationary, slow


def process_segment(seg_dir, accum_by_date, seg_date):
    """Parse one segment's qlog, accumulate into per-date dict.

    seg_date 由调用方从目录名解析后传入（便于在打开文件前做日期过滤）。
    """
    qlog = find_qlog(seg_dir)
    if qlog is None:
        raise FileNotFoundError(f"未找到 qlog: {seg_dir}")

    acc = SegmentAccum(seg_date)

    v_ego = 0.0
    engaged = False

    lr = LogReader(qlog)
    for msg in lr:
        w = msg.which()
        ts_ns = msg.logMonoTime

        if w == "carState":
            cs = msg.carState
            if hasattr(cs, "vEgo"):
                v_ego = cs.vEgo
            # engaged 兜底来源：cruiseState.enabled（carControl 优先覆盖）
            cs_en = getattr(cs, "cruiseState", None)
            if cs_en is not None and hasattr(cs_en, "enabled"):
                engaged = cs_en.enabled
            # 每帧只积分一次，vEgo 取本帧真实速度
            acc.integrate(v_ego, engaged, ts_ns)

        elif w == "carControl":
            cc = msg.carControl
            if hasattr(cc, "enabled"):
                engaged = cc.enabled

        elif w == "selfdriveState":
            ss = msg.selfdriveState
            if hasattr(ss, "enabled"):
                engaged = ss.enabled

        # 事件来源：顶层 onroadEvents（carEvents / selfdriveState.events 已废弃）
        elif w == "onroadEvents":
            cur = set()
            for ev in msg.onroadEvents:
                try:
                    cur.add(str(ev.name))
                except Exception:
                    continue
            for name in EVENT_MAP:
                acc.register_edge(name, name in cur)

        # 前车指标来源：radarState.leadOne / leadTwo
        elif w == "radarState":
            rs = msg.radarState
            tailgate = stationary = slow = False
            for lead in (getattr(rs, "leadOne", None), getattr(rs, "leadTwo", None)):
                t, s, sl = _lead_active(lead, v_ego)
                tailgate = tailgate or t
                stationary = stationary or s
                slow = slow or sl
            acc.register_edge("tailgating", tailgate)
            acc.register_edge("leadCarStationary", stationary)
            acc.register_edge("leadCarSlow", slow)

        # 记录 engaged 状态跳变（用于接管计数），每帧按 ts_ns 去重
        acc.record_engaged_transition(engaged, ts_ns)

    seg_stats = acc.to_daily_drive_stats()
    if seg_stats["totalDistanceKm"] > 0:
        date_key = seg_stats["date"]
        if date_key not in accum_by_date:
            accum_by_date[date_key] = {k: 0 for k in seg_stats if k != "date"}
        daily = accum_by_date[date_key]
        for k, v in seg_stats.items():
            if k == "date":
                continue
            # 以下字段取「单 segment 最大值」，其余按日累加
            if k in ("maxSpeedKmh", "maxSegmentDistanceKm", "longestSegmentMinutes"):
                daily[k] = max(daily.get(k, 0), v)
            elif isinstance(v, (int, float)):
                daily[k] = daily.get(k, 0) + v


def compute_safety_score(daily):
    """Replicate the same scoring logic as AggregatedStats.calculateScore."""
    total = daily.get("totalDistanceKm", 0)
    takeovers = daily.get("takeovers", 0)
    warnings = (daily.get("collisionWarning", 0) +
                daily.get("tailgating", 0) +
                daily.get("leadCarEmergencyBrake", 0) +
                daily.get("leadCarSlow", 0) +
                daily.get("startReminder", 0) +
                daily.get("laneChangeAssist", 0))
    score = 100
    if total > 0:
        score -= int((takeovers / (total / 1000.0)) * 2)
        score -= int(warnings / (total / 100.0))
    return max(0, min(100, score))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="C3 驾驶统计计算")
    parser.add_argument("--days", type=int, default=30,
                        help="仅统计最近 N 天的 segment（默认 30）")
    parser.add_argument("--all", action="store_true",
                        help="忽略日期过滤，处理全部 segment")
    parser.add_argument("--src", type=str, default=REALDATA,
                        help="指定 realdata 目录（默认 /data/media/0/realdata）")
    args = parser.parse_args()

    seg_dirs = sorted(
        d for d in glob.glob(os.path.join(args.src, "*--*"))
        if os.path.isdir(d)
    )

    if not seg_dirs:
        print(json.dumps([]))
        return

    # 日期过滤：从目录名解析 segment 日期，过期/无效的在打开文件前跳过，
    # 这样不会为全部 realdata 逐段解析而耗费数十秒。
    now = datetime.now(tz=timezone.utc)
    cutoff = (now - timedelta(days=args.days)).strftime("%Y-%m-%d")

    # Accumulate by date
    accum_by_date = {}
    ok = 0
    skipped = 0
    for d in seg_dirs:
        seg_name = os.path.basename(d)
        seg_date = parse_segment_date(d)
        if seg_date is None:
            skipped += 1
            continue                       # 时间戳无效 / 合成数据
        if not args.all and seg_date < cutoff:
            skipped += 1
            continue                       # 超出天数窗口
        try:
            process_segment(d, accum_by_date, seg_date)
            ok += 1
        except Exception as e:
            print(f"跳过 {seg_name}: {e}", file=sys.stderr)
            continue

    # Build output: one DriveStats-like object per date
    results = []
    for date_str in sorted(accum_by_date.keys(), reverse=True):
        daily = accum_by_date[date_str]
        daily["date"] = date_str
        # 消除多 segment 累加产生的浮点误差（如 9.999999999999998 → 10.0）
        for k, v in daily.items():
            if k == "date":
                continue
            if isinstance(v, float):
                daily[k] = round(v, 1)
        daily["safetyScore"] = compute_safety_score(daily)
        results.append(daily)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    if ok + skipped < len(seg_dirs):
        print(f"警告: {len(seg_dirs) - ok - skipped}/{len(seg_dirs)} 个 segment 处理失败", file=sys.stderr)


if __name__ == "__main__":
    main()
