#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
C3 设置中心桥接脚本 v2 — 按 C3 车机 UI 分类排列，支持中文。

用法：
    python settings_bridge.py list
    python settings_bridge.py get <key>
    python settings_bridge.py set <key> <value>
"""
import argparse
import json
import os
import sys

PARAMS_DIR = "/data/params/d"


class SimpleParams:
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
        with open(self._path(key), "w", encoding="utf-8") as f:
            f.write(str(value))

    def put_bool(self, key: str, value: bool) -> None:
        self.put(key, "1" if value else "0")

    def put_float(self, key: str, value: float) -> None:
        self.put(key, str(value))

    def get_float(self, key: str) -> float:
        try:
            return float(self.get(key))
        except (ValueError, RuntimeError):
            return 0.0


Params = SimpleParams
try:
    sys.path.insert(0, "/data/openpilot")
    from common.params import Params as _Params
    Params = _Params
except Exception:
    pass


# ==================== 设置项定义 ====================
# 按 C3 车机 UI 分类排列，与 sunnypilot SettingsWindowSP 的侧边栏顺序一致
# type: bool / int / float
# category: 分类标题（中文）
# choices: int 类型时的选项标签列表

SUPPORTED_SETTINGS = {}

def _def(key, type_, category, title, desc, **kwargs):
    SUPPORTED_SETTINGS[key] = {"type": type_, "category": category, "title": title, "desc": desc, **kwargs}


# ──────────── 1. 驾驶开关 (Toggles) ────────────
CAT_TOGGLES = "驾驶开关"

_def("OpenpilotEnabledToggle", "bool", CAT_TOGGLES,
     "启用 sunnypilot",
     "开启后使用 openpilot 系统进行自适应巡航和车道保持辅助。")

_def("ExperimentalMode", "bool", CAT_TOGGLES,
     "实验模式",
     "使用端到端纵向控制和新可视化。")

_def("DynamicExperimentalControl", "bool", CAT_TOGGLES,
     "动态实验控制",
     "由模型自动决定使用 ACC 还是端到端控制。")

_def("DisengageOnAccelerator", "bool", CAT_TOGGLES,
     "踩油门时解除接合",
     "开启后，踩下油门踏板将解除 openpilot。")

_def("IsLdwEnabled", "bool", CAT_TOGGLES,
     "车道偏离警告",
     "未打转向灯时偏离车道线将收到警报。")

_def("AlwaysOnDM", "bool", CAT_TOGGLES,
     "始终开启驾驶员监控",
     "即使 openpilot 未接合也监控驾驶员状态。")

_def("RecordFront", "bool", CAT_TOGGLES,
     "录制驾驶员摄像头",
     "上传驾驶员面部摄像头数据，帮助改进驾驶员监控。")

_def("RecordAudio", "bool", CAT_TOGGLES,
     "录制麦克风音频",
     "录制并存储行车过程中的麦克风音频。")

_def("IsMetric", "bool", CAT_TOGGLES,
     "使用公制单位",
     "以 km/h 显示速度，代替 mph。")


# ──────────── 2. 驾驶风格 ────────────
CAT_PERSONALITY = "驾驶风格"

_def("LongitudinalPersonality", "int", CAT_PERSONALITY,
     "驾驶风格",
     "Standard 为推荐。Aggressive 跟车更近；Relaxed 保持更远距离。",
     choices=["激进", "标准", "放松"])


# ──────────── 3. 转向设置 (Steering) ────────────
CAT_STEERING = "转向设置"

_def("Mads", "bool", CAT_STEERING,
     "MADS 模块化辅助驾驶",
     "开启 MADS（模块化辅助驾驶系统），支持仅横向或仅纵向控制。")

_def("MadsSteeringMode", "int", CAT_STEERING,
     "刹车时转向行为",
     "踩刹车后方向盘行为：保持控制 / 暂停 / 脱离。",
     choices=["保持", "暂停", "脱离"])

_def("MadsMainCruiseAllowed", "bool", CAT_STEERING,
     "巡航按钮切换 MADS",
     "允许通过主巡航按钮在 ACC 和 MADS 之间切换。")

_def("AutoLaneChangeTimer", "int", CAT_STEERING,
     "自动变道模式",
     "打转向灯后的自动变道模式：关闭 / 轻推 / 无轻推 / 延迟1-5秒。",
     choices=["关闭", "轻推(Nudge)", "无轻推", "1秒", "2秒", "3秒", "4秒", "5秒"])

_def("BlinkerPauseLateralControl", "bool", CAT_STEERING,
     "打灯暂停横向控制",
     "开启后，打转向灯时暂停方向盘控制。")

_def("NeuralNetworkLateralControl", "bool", CAT_STEERING,
     "神经网络横向控制",
     "使用模型直接输出横向控制，替代 PID 控制器。")

_def("LagdToggle", "bool", CAT_STEERING,
     "实时学习转向延迟",
     "开启后自动学习并补偿转向执行延迟。")


# ──────────── 4. 巡航设置 (Cruise) ────────────
CAT_CRUISE = "巡航设置"

_def("LaneTurnDesire", "bool", CAT_CRUISE,
     "弯道减速",
     "进入弯道前自动降低车速，提高过弯安全性。")

_def("LaneTurnValue", "float", CAT_CRUISE,
     "弯道速度阈值 (mph)",
     "弯道减速的目标车速（英里/小时），值越小过弯越慢。")

_def("CustomAccIncrementsEnabled", "bool", CAT_CRUISE,
     "自定义巡航增量",
     "开启后使用下方自定义的短按/长按速度增量。")

_def("CustomAccShortPressIncrement", "int", CAT_CRUISE,
     "短按速度增量 (mph)",
     "巡航中短按 +/- 按钮的速度变化量。",
     choices=["1", "2", "3", "4", "5"])

_def("CustomAccLongPressIncrement", "int", CAT_CRUISE,
     "长按速度增量 (mph)",
     "巡航中长按 +/- 按钮的速度变化量。",
     choices=["5", "8", "10", "15", "20"])


# ──────────── 5. 视觉设置 (Visuals) ────────────
CAT_VISUALS = "视觉设置"

_def("AccelBar", "bool", CAT_VISUALS,
     "加速指示条",
     "屏幕底部显示车辆加速/减速状态的横向指示条。")

_def("TurnSignal", "bool", CAT_VISUALS,
     "转向灯信号",
     "HUD 上显示转向灯状态指示。")

_def("SpeedLimit", "bool", CAT_VISUALS,
     "限速显示",
     "HUD 上显示当前道路限速信息。")

_def("RoadNameDisplay", "bool", CAT_VISUALS,
     "道路名称",
     "HUD 上显示当前道路名称。")

_def("SteeringArc", "bool", CAT_VISUALS,
     "转向弧线",
     "HUD 上显示预测的转向路径弧线。")

_def("StandstillTimer", "bool", CAT_VISUALS,
     "静止计时器",
     "停车等待时显示已停止的累计时间。")

_def("ChevronInfo", "int", CAT_VISUALS,
     "前车标识信息",
     "跟车时前车上方显示的信息类型。",
     choices=["关闭", "距离", "速度", "相对速度", "完整信息"])

_def("DevUIInfo", "int", CAT_VISUALS,
     "开发者 UI",
     "显示开发者调试面板，查看实时数据。",
     choices=["关闭", "底部", "右侧", "全部"])


# ──────────── 6. SP 功能 ────────────
CAT_SP = "SP 功能"

_def("MadsUnifiedEngagementMode", "bool", CAT_SP,
     "统一介入模式",
     "使用统一的接合/解除逻辑，简化操作。")

_def("QuietMode", "bool", CAT_SP,
     "静音模式",
     "关闭所有 sunnypilot 的提示音和语音。")

_def("RainbowMode", "bool", CAT_SP,
     "彩虹模式",
     "在屏幕上周期性切换颜色主题（仅供娱乐）。")

_def("ShowAdvancedControls", "bool", CAT_SP,
     "显示高级控制项",
     "在车机 UI 中显示更多 sunnypilot 高级调试选项。")


# ==================== 命令处理 ====================

def _params():
    return Params()


def cmd_list():
    p = _params()
    result = []
    for key, meta in SUPPORTED_SETTINGS.items():
        try:
            if meta["type"] == "bool":
                value = p.get_bool(key)
            elif meta["type"] == "float":
                value = p.get_float(key)
            else:
                raw = p.get(key)
                value = int(raw) if raw.strip() else 0
        except Exception as e:
            value = None
            error = str(e)
        else:
            error = None
        item = {"key": key, "value": value, "error": error}
        item.update(meta)
        result.append(item)
    print(json.dumps(result, ensure_ascii=False))


def cmd_get(key):
    meta = SUPPORTED_SETTINGS.get(key)
    if meta is None:
        print(json.dumps({"error": f"不支持的参数: {key}"}, ensure_ascii=False))
        sys.exit(1)
    p = _params()
    try:
        if meta["type"] == "bool":
            value = p.get_bool(key)
        elif meta["type"] == "float":
            value = p.get_float(key)
        else:
            value = int(p.get(key))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"key": key, "value": value}, ensure_ascii=False))


def cmd_set(key, value):
    meta = SUPPORTED_SETTINGS.get(key)
    if meta is None:
        print(json.dumps({"error": f"不支持的参数: {key}"}, ensure_ascii=False))
        sys.exit(1)
    p = _params()
    try:
        t = meta["type"]
        if t == "bool":
            v = str(value).lower() in ("1", "true", "yes", "on")
            p.put_bool(key, v)
        elif t == "float":
            p.put_float(key, float(value))
        else:
            p.put(key, str(int(value)))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(1)
    print(json.dumps({"success": True, "key": key, "value": value}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="C3 设置中心桥接脚本 v2")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    get_p = sub.add_parser("get")
    get_p.add_argument("key")
    set_p = sub.add_parser("set")
    set_p.add_argument("key")
    set_p.add_argument("value")
    args = parser.parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "get":
        cmd_get(args.key)
    elif args.command == "set":
        cmd_set(args.key, args.value)


if __name__ == "__main__":
    main()
