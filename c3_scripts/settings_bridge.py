#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C3 设置中心桥接脚本。

App 通过 SSH 调用本脚本来读写 C3 的 Params 参数。

用法：
    python settings_bridge.py list                    # 列出所有支持项
    python settings_bridge.py get <key>             # 读取单个参数
    python settings_bridge.py set <key> <value>       # 写入单个参数
"""
import argparse
import json
import os
import sys


PARAMS_DIR = "/data/params/d"


class SimpleParams:
    """不依赖 openpilot 库的 Params 轻量实现，直接读写 /data/params/d/ 文件。"""

    def _path(self, key: str) -> str:
        return os.path.join(PARAMS_DIR, key)

    def get(self, key: str) -> str:
        try:
            with open(self._path(key), "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""
        except Exception as e:
            raise RuntimeError(f"读取 {key} 失败: {e}") from e

    def get_bool(self, key: str) -> bool:
        return self.get(key) == "1"

    def put(self, key: str, value: str) -> None:
        os.makedirs(PARAMS_DIR, exist_ok=True)
        path = self._path(key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(str(value))
        except Exception as e:
            raise RuntimeError(f"写入 {key} 失败: {e}") from e

    def put_bool(self, key: str, value: bool) -> None:
        self.put(key, "1" if value else "0")


# 优先尝试导入 openpilot 的 Params，失败则使用 SimpleParams
Params = SimpleParams
try:
    sys.path.insert(0, "/data/openpilot")
    from common.params import Params as _Params

    Params = _Params
except Exception as e:
    # 使用 SimpleParams，避免依赖 openpilot/zmq
    pass



# v1 支持的设置项：key -> (UI 类型, 标题, 描述, 额外元数据)
SUPPORTED_SETTINGS = {
    "OpenpilotEnabledToggle": {
        "type": "bool",
        "title": "Enable openpilot",
        "desc": "Use the openpilot system for adaptive cruise control and lane keep driver assistance.",
    },
    "ExperimentalMode": {
        "type": "bool",
        "title": "Experimental Mode",
        "desc": "Use experimental longitudinal control.",
    },
    "DisengageOnAccelerator": {
        "type": "bool",
        "title": "Disengage on Accelerator Pedal",
        "desc": "When enabled, pressing the accelerator pedal will disengage openpilot.",
    },
    "IsLdwEnabled": {
        "type": "bool",
        "title": "Enable Lane Departure Warnings",
        "desc": "Receive alerts when the vehicle drifts over a detected lane line without a turn signal.",
    },
    "AlwaysOnDM": {
        "type": "bool",
        "title": "Always-On Driver Monitoring",
        "desc": "Enable driver monitoring even when openpilot is not engaged.",
    },
    "RecordFront": {
        "type": "bool",
        "title": "Record and Upload Driver Camera",
        "desc": "Upload data from the driver facing camera to help improve driver monitoring.",
    },
    "IsMetric": {
        "type": "bool",
        "title": "Use Metric System",
        "desc": "Display speed in km/h instead of mph.",
    },
    "RecordAudio": {
        "type": "bool",
        "title": "Record Microphone Audio",
        "desc": "Record and store microphone audio while driving.",
    },
    "AccelBar": {
        "type": "bool",
        "title": "Acceleration Bar",
        "desc": "Show a bottom-center horizontal bar indicating vehicle acceleration and deceleration.",
    },
    "LongitudinalPersonality": {
        "type": "int",
        "title": "Driving Personality",
        "desc": "Standard is recommended. Aggressive follows closer; Relaxed stays further away.",
        "choices": ["Aggressive", "Standard", "Relaxed"],
    },
    "DevUIInfo": {
        "type": "int",
        "title": "Developer UI",
        "desc": "Show a developer debug overlay with live values.",
        "choices": ["Off", "Bottom", "Right", "Both"],
    },
}


def _params():
    return Params()


def cmd_list():
    p = _params()
    result = []
    for key, meta in SUPPORTED_SETTINGS.items():
        try:
            if meta["type"] == "bool":
                value = p.get_bool(key)
            else:
                value = p.get(key)
        except Exception as e:
            value = None
            error = str(e)
        else:
            error = None
        item = {
            "key": key,
            "value": value,
            "error": error,
        }
        item.update(meta)
        result.append(item)
    print(json.dumps(result, ensure_ascii=False))


def cmd_get(key: str):
    meta = SUPPORTED_SETTINGS.get(key)
    if meta is None:
        print(json.dumps({"error": f"不支持的参数: {key}"}))
        sys.exit(1)
    p = _params()
    try:
        value = p.get_bool(key) if meta["type"] == "bool" else p.get(key)
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    print(json.dumps({"key": key, "value": value}, ensure_ascii=False))


def cmd_set(key: str, value: str):
    meta = SUPPORTED_SETTINGS.get(key)
    if meta is None:
        print(json.dumps({"error": f"不支持的参数: {key}"}))
        sys.exit(1)
    p = _params()
    try:
        if meta["type"] == "bool":
            # 支持 "true"/"1"/"false"/"0"
            v = value.lower() in ("1", "true", "yes", "on")
            p.put_bool(key, v)
        else:
            p.put(key, int(value))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    print(json.dumps({"success": True, "key": key, "value": value}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="C3 设置中心桥接脚本")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="列出所有支持的设置项")
    get_parser = sub.add_parser("get", help="读取单个参数")
    get_parser.add_argument("key", help="参数 key")
    set_parser = sub.add_parser("set", help="写入单个参数")
    set_parser.add_argument("key", help="参数 key")
    set_parser.add_argument("value", help="参数值")
    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "get":
        cmd_get(args.key)
    elif args.command == "set":
        cmd_set(args.key, args.value)


if __name__ == "__main__":
    main()
