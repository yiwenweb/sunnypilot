#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SunnyPilot 横向参数离线分析与导出脚本。

不修改 C3 的 /data/params/d/ 任何参数，只读取当前参数和 realdata 日志，
生成一份人类可读的文本报告，供用户确认后再决定是否手动应用。

用法示例：
    cd /data/openpilot && python3 c3_scripts/lateral_tune_export.py
    python3 c3_scripts/lateral_tune_export.py --max-segments 10 --mode qlog
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, "/data/openpilot")

from cereal import car, log
from openpilot.common.params import Params
from openpilot.tools.lib.logreader import LogReader


REALDATA_DIR = "/data/media/0/realdata"
OUTPUT_DIR = "/data/media/0"


def median_or_none(values):
    """返回列表中位数，空列表返回 None。"""
    if not values:
        return None
    return float(np.median(values))


def read_current_params(params: Params):
    """读取当前 C3 上的横向相关参数。"""
    current = {}

    # LiveParametersV2 (capnp bytes)
    lp_data = params.get("LiveParametersV2")
    if lp_data is not None:
        try:
            with log.Event.from_bytes(lp_data) as msg:
                lp = msg.liveParameters
                current["steerRatio"] = lp.steerRatio
                current["stiffnessFactor"] = lp.stiffnessFactor
                current["angleOffsetDeg"] = lp.angleOffsetDeg
                current["angleOffsetAverageDeg"] = lp.angleOffsetAverageDeg
                current["steerRatioValid"] = lp.steerRatioValid
                current["stiffnessFactorValid"] = lp.stiffnessFactorValid
                current["angleOffsetValid"] = lp.angleOffsetValid
                current["angleOffsetAverageValid"] = lp.angleOffsetAverageValid
                current["liveParametersValid"] = lp.valid
        except Exception as e:
            current["liveParametersError"] = str(e)

    # 旧版 LiveParameters (JSON) 兜底
    if lp_data is None:
        lp_old = params.get("LiveParameters")
        if lp_old is not None and isinstance(lp_old, dict):
            try:
                current["steerRatio"] = lp_old.get("steerRatio")
                current["stiffnessFactor"] = lp_old.get("stiffnessFactor")
                current["angleOffsetDeg"] = lp_old.get("angleOffsetDeg")
            except Exception as e:
                current["liveParametersError"] = str(e)

    # LiveTorqueParameters (capnp bytes)
    lt_data = params.get("LiveTorqueParameters")
    if lt_data is not None:
        try:
            with log.Event.from_bytes(lt_data) as msg:
                ltp = msg.liveTorqueParameters
                current["latAccelFactor"] = ltp.latAccelFactorFiltered
                current["latAccelOffset"] = ltp.latAccelOffsetFiltered
                current["friction"] = ltp.frictionCoefficientFiltered
                current["torqueLiveValid"] = ltp.liveValid
                current["torqueCalPerc"] = ltp.calPerc
        except Exception as e:
            current["liveTorqueParametersError"] = str(e)

    # LiveDelay (capnp bytes)
    ld_data = params.get("LiveDelay")
    if ld_data is not None:
        try:
            with log.Event.from_bytes(ld_data) as msg:
                ld = msg.liveDelay
                current["lateralDelay"] = ld.lateralDelay
                current["delayValidBlocks"] = ld.validBlocks
                current["delayCalPerc"] = ld.calPerc
        except Exception as e:
            current["liveDelayError"] = str(e)

    # CarParams 用于 steerActuatorDelay 和车型
    cp_data = params.get("CarParams")
    if cp_data is not None:
        try:
            with car.CarParams.from_bytes(cp_data) as cp:
                current["steerActuatorDelay"] = cp.steerActuatorDelay
                current["carFingerprint"] = cp.carFingerprint
        except Exception as e:
            current["carParamsError"] = str(e)

    return current


def find_segment_dirs(realdata_dir: str, max_segments: int):
    """返回 realdata 下按修改时间倒序的最新的 max_segments 个 segment 目录。"""
    base = Path(realdata_dir)
    if not base.exists():
        return []

    seg_dirs = []
    for path in base.iterdir():
        if path.is_dir():
            seg_dirs.append((path.stat().st_mtime, path))
    seg_dirs.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in seg_dirs[:max_segments]]


def find_log_file(seg_dir: Path, mode: str = "qlog"):
    """在 segment 目录下查找可用的日志文件。"""
    candidates = []
    if mode in ("auto", "rlog"):
        candidates.extend(["rlog.zst", "rlog.bz2", "rlog"])
    if mode in ("auto", "qlog"):
        candidates.extend(["qlog.zst", "qlog.bz2", "qlog"])

    for name in candidates:
        p = seg_dir / name
        if p.exists():
            return str(p)
    return None


def analyze_segments(seg_dirs, mode: str = "qlog"):
    """
    读取每个 segment 的 qlog/rlog，收集 online learning 过程中估计出来的参数。
    这里不做复杂的离线训练，而是把 C3 已经算出来的中间值做汇总统计。
    """
    records = {
        "steerRatio": [],
        "stiffnessFactor": [],
        "angleOffsetDeg": [],
        "angleOffsetAverageDeg": [],
        "latAccelFactor": [],
        "latAccelOffset": [],
        "friction": [],
        "lateralDelay": [],
    }
    per_segment = []

    for seg_dir in seg_dirs:
        seg_record = {"segment": seg_dir.name, "log": None, "samples": 0, "error": None}
        log_file = find_log_file(seg_dir, mode)
        if log_file is None:
            per_segment.append(seg_record)
            continue

        seg_record["log"] = os.path.basename(log_file)
        try:
            lr = LogReader(log_file)
            for msg in lr:
                which = msg.which()
                if which == "liveParameters":
                    lp = msg.liveParameters
                    if lp.valid:
                        if lp.steerRatioValid:
                            records["steerRatio"].append(lp.steerRatio)
                            seg_record["samples"] += 1
                        if lp.stiffnessFactorValid:
                            records["stiffnessFactor"].append(lp.stiffnessFactor)
                        if lp.angleOffsetValid:
                            records["angleOffsetDeg"].append(lp.angleOffsetDeg)
                        if lp.angleOffsetAverageValid:
                            records["angleOffsetAverageDeg"].append(lp.angleOffsetAverageDeg)
                elif which == "liveTorqueParameters":
                    ltp = msg.liveTorqueParameters
                    if ltp.liveValid:
                        records["latAccelFactor"].append(ltp.latAccelFactorFiltered)
                        records["latAccelOffset"].append(ltp.latAccelOffsetFiltered)
                        records["friction"].append(ltp.frictionCoefficientFiltered)
                elif which == "liveDelay":
                    ld = msg.liveDelay
                    if ld.validBlocks > 0:
                        records["lateralDelay"].append(ld.lateralDelay)
        except Exception as e:
            seg_record["error"] = str(e)

        per_segment.append(seg_record)

    proposed = {k: median_or_none(v) for k, v in records.items()}
    return proposed, per_segment, records


def format_report(current, proposed, per_segment, records):
    """把当前参数、建议参数、统计信息格式化成文本报告。"""
    lines = []
    lines.append("=" * 60)
    lines.append("SunnyPilot 横向参数分析报告")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 60)
    lines.append("")

    lines.append("[当前 C3 参数]")
    for k in [
        "carFingerprint",
        "steerActuatorDelay",
        "steerRatio",
        "stiffnessFactor",
        "angleOffsetDeg",
        "angleOffsetAverageDeg",
        "latAccelFactor",
        "latAccelOffset",
        "friction",
        "lateralDelay",
    ]:
        v = current.get(k)
        if v is not None:
            lines.append(f"{k} = {v}")
    for err_key in ["liveParametersError", "liveTorqueParametersError", "liveDelayError", "carParamsError"]:
        if err_key in current:
            lines.append(f"警告: 读取参数失败 [{err_key}]: {current[err_key]}")
    lines.append("")

    lines.append("[日志分析统计]")
    for seg in per_segment:
        err = seg.get("error")
        if err:
            lines.append(f"- {seg['segment']}: log={seg['log']}, samples={seg['samples']}, error={err}")
        else:
            lines.append(f"- {seg['segment']}: log={seg['log']}, samples={seg['samples']}")
    lines.append(f"总计有效 steerRatio 样本: {len(records['steerRatio'])}")
    lines.append(f"总计有效 torque 样本: {len(records['latAccelFactor'])}")
    lines.append(f"总计有效 delay 样本: {len(records['lateralDelay'])}")
    lines.append("")

    lines.append("[建议参数]")
    for k in [
        "steerRatio",
        "stiffnessFactor",
        "angleOffsetDeg",
        "angleOffsetAverageDeg",
        "latAccelFactor",
        "latAccelOffset",
        "friction",
        "lateralDelay",
    ]:
        v = proposed.get(k)
        cur = current.get(k)
        if v is not None:
            if cur is not None and cur != 0:
                diff_pct = (v - cur) / abs(cur) * 100
                lines.append(f"{k} = {v:.4f}  (当前 {cur:.4f}, 变化 {diff_pct:+.2f}%)")
            else:
                lines.append(f"{k} = {v:.4f}")
        else:
            lines.append(f"{k} = 无足够数据")
    lines.append("")

    lines.append("[说明]")
    lines.append("1. 本报告仅基于历史 qlog/rlog 中 online learning 的中间值做统计汇总。")
    lines.append("2. 未直接修改 C3 的 /data/params/d/ 任何参数。")
    lines.append("3. 建议先人工确认数值合理性，再决定是否手动应用到 C3。")
    lines.append("4. 如需应用，可将建议参数写入 LiveParametersV2 / LiveTorqueParameters / LiveDelay，")
    lines.append("   然后重启 openpilot / C3 使之生效。")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="SunnyPilot 横向参数分析导出")
    parser.add_argument("--segments-dir", default=REALDATA_DIR, help="realdata 目录")
    parser.add_argument("--max-segments", type=int, default=5, help="分析最近多少个 segment")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="报告输出目录")
    parser.add_argument("--mode", default="qlog", choices=["qlog", "rlog", "auto"], help="读取日志类型")
    args = parser.parse_args()

    params = Params()
    current = read_current_params(params)
    seg_dirs = find_segment_dirs(args.segments_dir, args.max_segments)
    proposed, per_segment, records = analyze_segments(seg_dirs, args.mode)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(args.output_dir, f"lateral_tune_report_{timestamp}.txt")
    os.makedirs(args.output_dir, exist_ok=True)

    report = format_report(current, proposed, per_segment, records)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(report)

    result = {
        "success": True,
        "path": output_file,
        "segments_analyzed": len(seg_dirs),
        "report": report,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
