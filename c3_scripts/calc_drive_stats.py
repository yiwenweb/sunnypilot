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
from datetime import datetime, timezone

sys.path.insert(0, "/data/openpilot")

try:
    from tools.lib.logreader import LogReader
except Exception as e:
    print("无法导入 LogReader，请确认在 /data/openpilot 下运行", file=sys.stderr)
    print(f"错误: {e}", file=sys.stderr)
    sys.exit(1)

REALDATA = "/data/media/0/realdata"
QLOG_NAMES = ("qlog.zst", "qlog.bz2", "qlog")

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
    "pedalPressed":       "takeovers",
    "steerOverride":      "takeovers",
    "gasPressedOverride": "takeovers",
}

# Events that represent a user takeover (engaged → disengaged)
TAKEOVER_EVENTS = {"pedalPressed", "steerOverride", "gasPressedOverride", "steerDisengage"}

# ---------------------------------------------------------------------------
# Per-segment accumulator
# ---------------------------------------------------------------------------
class SegmentAccum:
    __slots__ = ("total_m", "assisted_m", "first_ns", "last_ns",
                 "events", "prev_engaged", "prev_engaged_ns",
                 "start_ns", "segment_date", "_last_cs")

    def __init__(self, date_str):
        self.segment_date = date_str
        self.total_m = 0.0
        self.assisted_m = 0.0
        self.first_ns = None
        self.last_ns = None
        self.events = {}      # event_name → count
        self.prev_engaged = False
        self.prev_engaged_ns = None
        self.start_ns = None

    def register_car_state(self, cs, ts_ns):
        """Integrate distance from vEgo (m/s) × dt."""
        v_ego = cs.vEgo
        engaged = cs.cruiseState.enabled
        self._integrate(v_ego, engaged, ts_ns)

    def register_selfdrive_state(self, ss, cs, ts_ns):
        """Integrate using selfdriveState.enabled (newer openpilot)."""
        v_ego = cs.vEgo if cs else 0.0
        engaged = ss.enabled
        self._integrate(v_ego, engaged, ts_ns)

    def _integrate(self, v_ego, engaged, ts_ns):
        if self.start_ns is None:
            self.start_ns = ts_ns
            self.last_ns = ts_ns
            self.prev_engaged = engaged
            return

        dt_s = (ts_ns - self.last_ns) * 1e-9
        if dt_s <= 0 or dt_s > 5.0:
            # Clamp: skip absurd gaps (>5 sec = likely ignition cycle boundary)
            self.last_ns = ts_ns
            self.prev_engaged = engaged
            return

        avg_v = v_ego
        ds_m = avg_v * dt_s
        self.total_m += ds_m
        if engaged:
            self.assisted_m += ds_m

        self.last_ns = ts_ns
        self.prev_engaged = engaged

    def register_event(self, event_name):
        self.events[event_name] = self.events.get(event_name, 0) + 1

    def compute_duration_min(self):
        if self.start_ns is None or self.last_ns is None:
            return 0
        return int((self.last_ns - self.start_ns) * 1e-9 / 60)

    def to_daily_drive_stats(self):
        """Convert segment accumulator to a per-day stats dict (additive)."""
        manual_m = max(0.0, self.total_m - self.assisted_m)

        # Count takeovers from tracked events
        takeover_count = sum(self.events.get(e, 0) for e in TAKEOVER_EVENTS)

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
            "durationMinutes": self.compute_duration_min(),
            "takeovers": takeover_count,
            "collisionWarning": col_warn,
            "tailgating": 0,            # TODO: derive from lead distance
            "leadCarStationary": 0,      # TODO: derive from lead vEgo
            "leadCarEmergencyBrake": aeb_cnt,
            "leadCarSlow": 0,            # TODO: derive from lead vRel
            "startReminder": startup_cnt,
            "laneChangeAssist": lc_cnt,
            "safetyScore": 0,            # computed later in aggregation
        }


def find_qlog(seg_dir):
    for name in QLOG_NAMES:
        p = os.path.join(seg_dir, name)
        if os.path.isfile(p):
            return p
    return None


def parse_segment_date(seg_dir_name):
    """
    Segment dir name: <start_timestamp>--<route_hash>--<seg_idx>
    The timestamp is a Unix epoch (seconds).
    """
    try:
        ts_str = seg_dir_name.split("--")[0]
        ts = int(ts_str)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        return None


def process_segment(seg_dir, accum_by_date):
    """Parse one segment's qlog, accumulate into per-date dict."""
    qlog = find_qlog(seg_dir)
    if qlog is None:
        raise FileNotFoundError(f"未找到 qlog: {seg_dir}")

    seg_date = parse_segment_date(os.path.basename(seg_dir))
    if seg_date is None:
        seg_date = "unknown"

    acc = SegmentAccum(seg_date)

    lr = LogReader(qlog)
    for msg in lr:
        w = msg.which()
        ts_ns = msg.logMonoTime

        # Track the most recent carState for vEgo
        if w == "carState":
            cs = msg.carState
            if hasattr(cs, 'vEgo'):
                acc.register_car_state(cs, ts_ns)

        # Track engaged from selfdriveState (newer) or carControl
        if w == "selfdriveState":
            ss = msg.selfdriveState
            # Re-use last carState for vEgo if available; use 0 as fallback
            acc.register_selfdrive_state(ss, getattr(acc, '_last_cs', None), ts_ns)

        if w == "carControl":
            cc = msg.carControl
            v_ego = getattr(acc, '_last_v_ego', 0.0)
            if hasattr(cc, 'enabled'):
                acc._integrate(v_ego, cc.enabled, ts_ns)

        # Parse carEvents
        if w == "carEvents":
            for ev in msg.carEvents:
                try:
                    name = str(ev.name)
                except Exception:
                    continue
                if name in EVENT_MAP:
                    acc.register_event(name)

        if w == "selfdriveState":
            ss = msg.selfdriveState
            if hasattr(ss, 'events'):
                for ev in ss.events:
                    try:
                        name = str(ev.name)
                    except Exception:
                        continue
                    if name in EVENT_MAP:
                        acc.register_event(name)

        # Keep last carState around for selfdriveState integration
        if w == "carState":
            acc._last_cs = msg.carState

    seg_stats = acc.to_daily_drive_stats()
    if seg_stats["totalDistanceKm"] > 0:
        date_key = seg_stats["date"]
        if date_key not in accum_by_date:
            accum_by_date[date_key] = {k: 0 for k in seg_stats if k != "date"}
        for k, v in seg_stats.items():
            if k == "date":
                continue
            if isinstance(v, (int, float)):
                accum_by_date[date_key][k] = accum_by_date[date_key].get(k, 0) + v


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
    seg_dirs = sorted(
        d for d in glob.glob(os.path.join(REALDATA, "*--*"))
        if os.path.isdir(d)
    )

    if not seg_dirs:
        print(json.dumps([]))
        return

    # Accumulate by date
    accum_by_date = {}
    ok = 0
    for d in seg_dirs:
        seg_name = os.path.basename(d)
        try:
            process_segment(d, accum_by_date)
            ok += 1
        except Exception as e:
            print(f"跳过 {seg_name}: {e}", file=sys.stderr)
            continue

    # Build output: one DriveStats-like object per date
    results = []
    for date_str in sorted(accum_by_date.keys(), reverse=True):
        daily = accum_by_date[date_str]
        daily["date"] = date_str
        daily["safetyScore"] = compute_safety_score(daily)
        results.append(daily)

    print(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"处理完成: {ok}/{len(seg_dirs)} 个 segment", file=sys.stderr)


if __name__ == "__main__":
    main()
