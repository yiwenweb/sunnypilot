#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C3 端行车记录仪预处理脚本。

功能：
  - 读取 segment 的 qlog.zst
  - 按 logMonoTime 对齐，抽取出每一帧需要在 App 上叠加的模型/车辆/状态数据
  - 生成 overlay.json，供 App 下载后做视频回放叠加

在 C3 设备上运行示例：
    cd /data/openpilot
    python /tmp/preprocess_recorder.py /data/media/0/realdata/00000000--1cdc29fe39--0

输出：
    <segment>/overlay.json
"""
import os
import sys
import json
import glob
import argparse
from pathlib import Path

sys.path.insert(0, "/data/openpilot")

try:
    from tools.lib.logreader import LogReader
    from common.transformations.camera import DEVICE_CAMERAS
except Exception as e:
    print("无法导入 LogReader，请确认在 /data/openpilot 下运行")
    print("错误:", e)
    sys.exit(1)


REALDATA = "/data/media/0/realdata"
QLOG_NAMES = ("qlog.zst", "qlog.bz2", "qlog")
VIDEO_NAME = "qcamera.ts"

# 只保留最近几次模型输出里的采样点，减少 JSON 体积
PATH_SAMPLE_EVERY = 2


def _xyz_to_list(xyz):
    """把 capnp XYZTData 的 x/y/z 转成普通 list，并按采样间隔稀疏化"""
    return {
        "x": list(xyz.x)[::PATH_SAMPLE_EVERY],
        "y": list(xyz.y)[::PATH_SAMPLE_EVERY],
        "z": list(xyz.z)[::PATH_SAMPLE_EVERY],
    }


def extract_model_v2(m):
    return {
        "frameId": int(m.frameId),
        "timestampEof": int(m.timestampEof),
        "position": _xyz_to_list(m.position),
        "laneLines": [_xyz_to_list(ll) for ll in m.laneLines],
        "laneLineProbs": list(m.laneLineProbs),
        "roadEdges": [_xyz_to_list(re) for re in m.roadEdges],
        "roadEdgeStds": list(m.roadEdgeStds),
        "leadsV3": [
            {
                "prob": float(lead.prob),
                "x": list(lead.x),
                "y": list(lead.y),
                "xStd": list(lead.xStd),
            }
            for lead in m.leadsV3
        ],
        "acceleration": {
            "x": list(m.acceleration.x)[::PATH_SAMPLE_EVERY],
        },
    }


def extract_radar_state(rs):
    def _lead(ld):
        return {
            "status": bool(ld.status),
            "dRel": float(ld.dRel),
            "yRel": float(ld.yRel),
            "vRel": float(ld.vRel),
            "vLead": float(ld.vLead),
        }
    return {
        "leadOne": _lead(rs.leadOne),
        "leadTwo": _lead(rs.leadTwo),
    }


def extract_car_state(cs):
    cr = cs.cruiseState
    return {
        "vEgo": float(cs.vEgo),
        "aEgo": float(cs.aEgo),
        "steeringAngleDeg": float(cs.steeringAngleDeg),
        "cruiseState": {
            "available": bool(cr.available),
            "enabled": bool(cr.enabled),
            "speed": float(cr.speed),
        },
    }


def extract_controls_state(cs):
    return {
        "longControlState": str(cs.longControlState),
    }


def extract_selfdrive_state(ss):
    return {
        "enabled": bool(ss.enabled),
        "active": bool(ss.active),
        "state": str(ss.state),
        "alertText1": str(ss.alertText1),
        "alertText2": str(ss.alertText2),
        "experimentalMode": bool(ss.experimentalMode),
    }


def extract_longitudinal_plan(lp):
    return {
        "allowThrottle": bool(lp.allowThrottle),
        "accels": list(lp.accels)[:10],
    }


def extract_live_calibration(lc):
    return {
        "rpyCalib": list(lc.rpyCalib) if len(lc.rpyCalib) == 3 else [0.0, 0.0, 0.0],
        "height": list(lc.height)[:1] if len(lc.height) else [1.22],
    }


def find_qlog(seg_dir):
    for name in QLOG_NAMES:
        p = os.path.join(seg_dir, name)
        if os.path.isfile(p):
            return p
    return None


def process_segment(seg_dir, out_path=None):
    seg_dir = Path(seg_dir)
    qlog = find_qlog(str(seg_dir))
    if qlog is None:
        raise FileNotFoundError(f"未找到 qlog: {seg_dir}")

    video_path = seg_dir / VIDEO_NAME
    if not video_path.exists():
        video_path = None

    if out_path is None:
        out_path = seg_dir / "overlay.json"

    frames = []
    last_model = None
    last_radar = None
    last_car = None
    last_controls = None
    last_selfdrive = None
    last_plan = None
    last_calib = None

    lr = LogReader(qlog)
    for msg in lr:
        w = msg.which()
        t = int(msg.logMonoTime)

        if w == "modelV2":
            last_model = extract_model_v2(msg.modelV2)
        elif w == "radarState":
            last_radar = extract_radar_state(msg.radarState)
        elif w == "carState":
            last_car = extract_car_state(msg.carState)
        elif w == "controlsState":
            last_controls = extract_controls_state(msg.controlsState)
        elif w == "selfdriveState":
            last_selfdrive = extract_selfdrive_state(msg.selfdriveState)
        elif w == "longitudinalPlan":
            last_plan = extract_longitudinal_plan(msg.longitudinalPlan)
        elif w == "liveCalibration":
            last_calib = extract_live_calibration(msg.liveCalibration)

        # 以 modelV2 为关键帧输出一帧叠加数据
        if w == "modelV2":
            frames.append({
                "logMonoTime": t,
                "modelV2": last_model,
                "radarState": last_radar,
                "carState": last_car,
                "controlsState": last_controls,
                "selfdriveState": last_selfdrive,
                "longitudinalPlan": last_plan,
                "liveCalibration": last_calib,
            })

    if not frames:
        raise ValueError(f"未从 qlog 中提取到任何 modelV2 帧: {seg_dir}")

    device_camera = DEVICE_CAMERAS.get(("tici", "ar0231"))
    camera_config = None
    if device_camera is not None:
        camera_config = {
            "fcam": {
                "width": int(device_camera.fcam.width),
                "height": int(device_camera.fcam.height),
                "focalLength": float(device_camera.fcam.focal_length),
            },
            "ecam": {
                "width": int(device_camera.ecam.width),
                "height": int(device_camera.ecam.height),
                "focalLength": float(device_camera.ecam.focal_length),
            },
        }

    output = {
        "version": 1,
        "segmentId": seg_dir.name,
        "videoFile": VIDEO_NAME,
        "videoPath": str(video_path) if video_path else None,
        "cameraConfig": camera_config,
        "frameCount": len(frames),
        "startMonoTime": frames[0]["logMonoTime"],
        "endMonoTime": frames[-1]["logMonoTime"],
        "frames": frames,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    print(f"已生成 {out_path}，共 {len(frames)} 帧")
    return out_path


def main():
    parser = argparse.ArgumentParser(description="预处理行车记录仪 segment，生成 overlay.json")
    parser.add_argument("segment", nargs="?", help="segment 目录，例如 /data/media/0/realdata/00000000--1cdc29fe39--0")
    parser.add_argument("--all", action="store_true", help="处理 /data/media/0/realdata 下所有 segment")
    parser.add_argument("--out", help="输出 JSON 路径，默认 <segment>/overlay.json")
    args = parser.parse_args()

    if args.all:
        seg_dirs = sorted([d for d in glob.glob(os.path.join(REALDATA, "*--*")) if os.path.isdir(d)])
        ok = 0
        for d in seg_dirs:
            try:
                process_segment(d)
                ok += 1
            except Exception as e:
                print(f"跳过 {d}: {e}")
        print(f"完成：{ok}/{len(seg_dirs)} 个 segment 处理成功")
    elif args.segment:
        process_segment(args.segment, args.out)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
