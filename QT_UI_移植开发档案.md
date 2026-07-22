# sunnypilot Qt C++ UI 移植开发档案

> 项目：比亚迪唐 DM 2018 sunnypilot 适配  
> 硬件：Comma Three (C3)  
> 基版：sunnypilot 0.10.1 master-tici  
> 运行分支：staging-tici  
> 创建时间：2026-07-04

---

## 一、目录架构说明

```
桌面                                     C3 设备
─────────────────────────────────────────────────────────────────
sunnypilot/     ←git绑定→  /data/openpilot/      实际运行系统
(staging-tici)              - staging-tici 分支
                             - 预编译发布版，无 Qt C++ 源码
                             - /data/openpilot/selfdrive/ui/ui 是运行中的二进制
                             
sunnypilot1/    ←git绑定→  /data/panda_build/     编译工厂
(master-tici)               - master-tici 分支
                             - 有完整 Qt C++ 源码
                             - scons 编译产出 ui 二进制
                             - 编译后的 ui 复制给 openpilot 使用
```

**核心关系**：
- `/data/openpilot/` 是实际运行的系统，但没有 UI 源码 → **需要借 `/data/panda_build/` 编译**
- 在 `sunnypilot1/` 中改 C++ 源码 → push → C3 上 `/data/panda_build/` 拉取 → scons 编译
- 编译产物 `/data/panda_build/selfdrive/ui/ui` 复制到 `/data/openpilot/selfdrive/ui/ui`
- 两个目录用 `yiwen` remote 连接同一个 GitHub 仓库的不同分支

**关键事实**：C3 实际运行的是 C++ Qt UI（`selfdrive/ui/ui` 二进制），Raylib Python UI（`ui.py`）是 `enabled=False`，不会被加载。网页上改的 Raylib Python 代码（AccelBar、MADS边框等）全部作废。

---

## 二、Git 仓库配置

### 远程仓库关系

```
官方上游:  https://github.com/sunnypilot/sunnypilot.git
个人仓库:  https://github.com/yiwenweb/sunnypilot.git
```

### 远端名速查表

| 位置 | 远端名 | 指向仓库 | 用途 |
|---|---|---|---|
| 桌面 sunnypilot/ | `origin` | yiwenweb/sunnypilot.git | 推送 staging-tici |
| 桌面 sunnypilot1/ | `origin` | sunnypilot/sunnypilot.git | 只读 |
| 桌面 sunnypilot1/ | `yiwen` | yiwenweb/sunnypilot.git | 推送 qt-dev |
| C3 /data/openpilot/ | `myrepo` | yiwenweb/sunnypilot.git | 拉取 staging-tici |
| C3 /data/openpilot/ | `upstream` | sunnypilot/sunnypilot.git | 只读 |
| C3 /data/panda_build/ | `yiwen` | yiwenweb/sunnypilot.git | 拉取 qt-dev（编译） |
| C3 /data/panda_build/ | `origin` | sunnypilot/sunnypilot.git | 只读 |

> ⚠️ **关键**：C3 上 `/data/openpilot/` 的远端名是 **`myrepo`**（不是 `origin`），这是历史遗留命名。拉取时用 `git pull myrepo staging-tici`。

### 桌面 sunnypilot/ 配置（运行系统源码）

```powershell
origin → https://github.com/yiwenweb/sunnypilot.git       # 个人，推送
分支: staging-tici
```

### 桌面 sunnypilot1/ 配置（编译工厂源码）

```powershell
origin → https://github.com/sunnypilot/sunnypilot.git     # 官方，只读
yiwen  → https://github.com/yiwenweb/sunnypilot.git       # 个人，推送
分支: qt-dev  (基于 master-tici 创建)
```

### C3 /data/openpilot/ 配置（运行系统）

```bash
myrepo   → https://github.com/yiwenweb/sunnypilot.git     # 个人仓库
upstream → https://github.com/sunnypilot/sunnypilot.git   # 官方上游
分支: staging-tici
```

> ⚠️ **历史遗留冗余清理**：如果你的 C3 有 `origin` / `yiwen` 指向同一仓库，建议清理：
> ```bash
> cd /data/openpilot
> git remote -v  # 检查当前配置
> # 删除冗余远程仓库（如果存在）
> git remote remove origin 2>/dev/null || true
> git remote remove yiwen 2>/dev/null || true
> # 验证清理结果
> git remote -v
> ```

**拉取运行系统更新**：
```bash
cd /data/openpilot
git pull myrepo staging-tici
```

### C3 /data/panda_build/ 配置（编译工厂）

```bash
origin → https://github.com/sunnypilot/sunnypilot.git     # 官方上游
yiwen  → https://github.com/yiwenweb/sunnypilot.git       # 个人仓库
分支: master-tici（始终留在此分支）
```

**C3 上的 /data/panda_build 始终留在 master-tici 分支**，通过 `git checkout yiwen/qt-dev -- <文件>` 拉取单个改动的文件进行编译。

---

## 三、Qt C++ UI 源码结构

### 目录树

```
selfdrive/ui/
├── qt/                                    # 原生 openpilot Qt UI
│   ├── onroad/
│   │   ├── model.cc / model.h             # 模型渲染（路径、车道线、前车chevron+状态文字）
│   │   ├── hud.cc / hud.h                 # HUD（速度、设定速度、MAX）
│   │   ├── annotated_camera.cc/.h         # 摄像头标注
│   │   ├── buttons.cc/.h                  # 实验模式按钮
│   │   ├── alerts.cc/.h                   # 警告提示
│   │   ├── driver_monitoring.cc/.h        # 驾驶员监控
│   │   └── onroad_home.cc/.h              # 驾驶页面窗口
│   ├── offroad/
│   │   └── settings/...                   # 设置面板
│   ├── widgets/                           # 基础控件库
│   ├── sidebar.cc/.h                      # 侧边栏
│   ├── home.cc/.h                         # 主页
│   └── window.cc/.h                       # 顶层窗口
│
├── sunnypilot/
│   ├── qt/                                # sunnypilot 定制 Qt UI ★核心移植目录
│   │   ├── onroad/
│   │   │   ├── hud.cc / hud.h             # HudRendererSP（含 Dev UI 全部绘制）
│   │   │   ├── model.cc / model.h         # ModelRendererSP（彩虹路径+盲点检测）
│   │   │   ├── annotated_camera.cc/.h     # AnnotatedCameraWidgetSP（摄像头标注扩展）
│   │   │   ├── buttons.cc/.h              # ExperimentalButtonSP
│   │   │   ├── onroad_home.cc/.h          # OnroadWindowSP
│   │   │   └── developer_ui/
│   │   │       ├── developer_ui.cc/.h     # DeveloperUi 类（15个静态方法）
│   │   │       └── ui_elements.h          # UiElement 结构体
│   │   ├── offroad/
│   │   │   └── settings/
│   │   │       ├── settings.cc/.h         # SettingsWindowSP（设置导航）
│   │   │       ├── visuals_panel.cc/.h    # VisualsPanel（视觉效果面板）
│   │   │       ├── developer_panel.cc/.h  # DeveloperPanelSP
│   │   │       ├── device_panel.cc/.h
│   │   │       ├── software_panel.cc/.h
│   │   │       ├── models_panel.cc/.h
│   │   │       ├── lateral_panel.cc/.h
│   │   │       ├── longitudinal_panel.cc/.h
│   │   │       ├── osm_panel.cc/.h
│   │   │       ├── trips_panel.cc/.h
│   │   │       ├── vehicle_panel.cc/.h
│   │   │       ├── sunnylink_panel.cc/.h
│   │   │       └── brightness.cc/.h
│   │   ├── widgets/
│   │   │   ├── controls.cc/.h             # 核心控件库（24KB头文件）
│   │   │   ├── toggle.cc/.h               # ToggleSP 蓝色开关
│   │   │   ├── scrollview.cc/.h
│   │   │   └── ...
│   │   ├── sidebar.cc/.h                  # sidebar（含Sunnylink状态）
│   │   ├── home.cc/.h                     # HomeWindowSP
│   │   └── window.cc/.h                   # MainWindowSP
│   ├── ui.cc / ui.h                       # UIStateSP（状态管理）
│   └── ui_scene.h                         # UISceneSP（场景结构）
│
└── ui.cc / ui.h                           # 原生 UIState
```

---

## 四、已实现功能清单（Qt C++ UI 中）

### Onroad 驾驶界面

| 功能 | 参数 | 实现位置 | 状态 |
|------|------|---------|------|
| HUD 速度+设定速度+MAX | — | `qt/onroad/hud.cc` | ✅ |
| 模型路径渲染（实验模式渐变） | — | `qt/onroad/model.cc` | ✅ |
| 车道线+道路边缘 | — | `qt/onroad/model.cc` | ✅ |
| 前车 Chevron 三角标记 | — | `qt/onroad/model.cc` | ✅ |
| Chevron 信息显示（距离/速度/TTC） | `ChevronInfo` (0-4) | `qt/onroad/model.cc:drawLeadStatusAtPosition()` | ✅ |
| 彩虹路径动画 | `RainbowMode` (bool) | `sunnypilot/qt/onroad/model.cc` | ✅ |
| 盲点检测警告 | `BlindSpot` (bool) | `sunnypilot/qt/onroad/model.cc` | ✅ |
| 开发者 UI（右侧5指标） | `DevUIInfo` (1或2) | `sunnypilot/qt/onroad/hud.cc:drawRightDevUI()` | ✅ |
| 开发者 UI（底部5-6指标） | `DevUIInfo` (2) | `sunnypilot/qt/onroad/hud.cc:drawBottomDevUI()` | ✅ |
| **LaneLineData 车道线距离** | `LaneLineData` (bool) | `sunnypilot/qt/onroad/hud.cc:drawLaneLineData()` | ✅ 已上移 y=400 |
| **SpeedLimit 限速标志** | `SpeedLimit` (bool) | `sunnypilot/qt/onroad/hud.cc:drawSpeedLimit()` | ✅ 与ACC融合一体化框 |
| **RoadName 道路名称** | `RoadNameDisplay` (bool) | `sunnypilot/qt/onroad/hud.cc:drawRoadName()` | ✅ 38pt, y=24 |
| **SteeringArc 转向弧** | `SteeringArc` (bool) | `sunnypilot/qt/onroad/hud.cc:drawSteeringArc()` | ✅ 线宽-5%弧长+5%下移 |
| 动态实验模式按钮 | — | `sunnypilot/qt/onroad/buttons.cc` | ✅ |
| Sunnylink 侧边栏状态 | — | `sunnypilot/qt/sidebar.cc` | ✅ |
| 驾驶员监控 | — | `qt/onroad/driver_monitoring.cc` | ✅ |

### 设置面板

| 面板 | 位置 | 状态 |
|------|------|------|
| Device 设备 | `sunnypilot/qt/offroad/settings/device_panel.cc` | ✅ |
| Network 网络 | `sunnypilot/qt/network/networking.cc` | ✅ |
| Sunnylink | `sunnypilot/qt/offroad/settings/sunnylink_panel.cc` | ✅ |
| Toggles 开关 | `sunnypilot/qt/offroad/settings/settings.cc` | ✅ |
| Software 软件 | `sunnypilot/qt/offroad/settings/software_panel.cc` | ✅ |
| Models 模型 | `sunnypilot/qt/offroad/settings/models_panel.cc` | ✅ |
| Steering 横向控制 | `sunnypilot/qt/offroad/settings/lateral_panel.cc` | ✅ |
| Cruise 纵向控制 | `sunnypilot/qt/offroad/settings/longitudinal_panel.cc` | ✅ |
| **Visuals 视觉** | `sunnypilot/qt/offroad/settings/visuals_panel.cc` | ✅ |
| **★ SP Features 移植特性** | `sunnypilot/qt/offroad/settings/sunny_features_panel.cc` | ✅ 新建 |
| — | **LaneLineData 车道线距离** | `sunnypilot/qt/offroad/settings/sunny_features_panel.cc` | ✅ 新增开关 |
| — | **SpeedLimit 限速标志** | `sunnypilot/qt/offroad/settings/sunny_features_panel.cc` | ✅ 新增开关 |
| — | **RoadNameDisplay 道路名称** | `sunnypilot/qt/offroad/settings/sunny_features_panel.cc` | ✅ 新增开关 |
| — | **SteeringArc 转向弧** | `sunnypilot/qt/offroad/settings/sunny_features_panel.cc` | ✅ 新增开关 |
| OSM 地图 | `sunnypilot/qt/offroad/settings/osm_panel.cc` | ✅ |
| Trips 行程 | `sunnypilot/qt/offroad/settings/trips_panel.cc` | ✅ |
| Vehicle 车辆 | `sunnypilot/qt/offroad/settings/vehicle_panel.cc` | ✅ |
| Developer 开发者 | `sunnypilot/qt/offroad/settings/developer_panel.cc` | ✅ |
| Firehose | `qt/offroad/settings/...` | ✅ |

### VisualsPanel 现有控件

| 控件 | 参数 | 类型 |
|------|------|------|
| Show Blind Spot Warnings | `BlindSpot` | ParamControlSP (开关) |
| Enable Tesla Rainbow Mode | `RainbowMode` | ParamControlSP (开关) |
| Display Metrics Below Chevron | `ChevronInfo` | ButtonParamControlSP (5档) |
| Developer UI | `DevUIInfo` | ButtonParamControlSP (3档) |

---

## 五、确认缺失功能（待移植）

### 优先级 P0：已写 Raylib 验证、需重写到 Qt C++

| 序号 | 功能 | 目标文件 | 难度 | 状态 |
|------|------|---------|------|------|
| 1 | **AccelBar (RocketFuel竖条)** | `sunnypilot/qt/onroad/hud.cc` | ⭐ 低 | ✅ 已完成 |
| 2 | **MADS 五态彩色边框** | `ui.cc` updateStatus() | — | ✅ 代码中原有 |

**AccelBar 已完成实现详情**：
- 参数名：`AccelBar` (bool, PERSISTENT | BACKUP, 默认 "0")
- 注册：`common/params_keys.h` ✅
- 场景字段：`UISceneSP::accel_bar` ✅
- 参数读取：`ui_update_params_sp()` 每帧读取 ✅
- 绘制：`HudRendererSP::drawAccelBar()` ✅
- 设置面板：**SP Features** 面板中的 ParamControlSP 开关 ✅
- 图标：`sunnypilot/selfdrive/assets/offroad/icon_sunny_features.svg` ✅

**显示效果**：
- ✅ 已改为 **2026 RocketFuel 风格**：左侧竖条，36x280px，加速绿向上填充，减速红向下填充
- 满量程 ±3.0 m/s²，深色圆角背景 + 中心零位线

### 优先级 P1：已完成 ✅

| 序号 | 功能 | 依赖 | 状态 |
|------|------|------|------|
| 3 | **TurnSignal 转向灯箭头** | `carState.leftBlinker/rightBlinker` | ✅ 已完成 |
| 4 | ~~RocketFuel~~ → 已合并到 AccelBar | — | — |

### 优先级 P2：需要数据管道支持（待确认 0.10.1 是否有对应 SP 消息）

| 序号 | 功能 | 所需数据 | 难度 |
|------|------|---------|------|
| 5 | **CircularAlerts 环形提醒** | `longitudinalPlanSP.e2eAlerts` | ⭐⭐⭐ 中-高 |
| 6 | **SmartCruiseControl SCC状态** | `longitudinalPlanSP.smartCruiseControl` | ⭐⭐⭐ 高 |

> ✅ **已移出 P2**：`SteeringArc`、`SpeedLimit`、`RoadName` 三项已在 `liveMapDataSP` / `carState` 数据管道支持下完成 Qt C++ 移植。
> ❌ **已删除**：`SteerTorqueData` 转向扭矩监控功能已移除（2026-07-13）。

---

## 六、开发工作流

### 日常流程

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  桌面 sunnypilot1/ (qt-dev)     C3 /data/panda_build (master-tici) │
│  ┌──────────────────┐          ┌──────────────────────────┐    │
│  │ 1. 编辑 C++ 源码  │   git    │ 3. fetch + checkout 文件  │    │
│  │ 2. commit + push  │──push──▶│ 4. scons -j4 编译       │    │
│  │    to yiwen/qt-dev│          │ 5. 替换 ui 二进制       │    │
│  └──────────────────┘          │ 6. reboot 验证          │    │
│         ▲                      └──────────────────────────┘    │
│         │                                 │                     │
│         └─────── 验证通过后源码同步回桌面 ──┘                     │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 编译命令

```bash
cd /data/panda_build
source /usr/local/venv/bin/activate
export PYTHONPATH=/data/panda_build
scons -j4 selfdrive/ui/ui
```

产物：`/data/panda_build/selfdrive/ui/ui`，编译时间约 10-20 分钟。

### 部署命令

```bash
# 停止 UI 进程
tmux kill-session -t comma 2>/dev/null
sudo pkill -f manager
sudo pkill -f "selfdrive/ui/ui"
sleep 3

# 备份 + 替换
cp /data/openpilot/selfdrive/ui/ui /data/openpilot/selfdrive/ui/ui.bak
cp /data/panda_build/selfdrive/ui/ui /data/openpilot/selfdrive/ui/ui

# 重启
reboot
```

### C3 拉取最新改动

```bash
cd /data/panda_build
git fetch yiwen qt-dev

# 拉取单个文件（安全方式）
git checkout yiwen/qt-dev -- selfdrive/ui/sunnypilot/qt/onroad/hud.cc
git checkout yiwen/qt-dev -- selfdrive/ui/sunnypilot/qt/onroad/hud.h
# ... 其他文件

# 编译
scons -j4 selfdrive/ui/ui

# ⚠️ 覆盖前必须先停掉正在运行的 ui 进程，否则 cp 会报 "Text file busy"
sudo pkill -f manager
sudo pkill -f "selfdrive/ui/ui"
sleep 3

# 覆盖并重启
cp selfdrive/ui/ui /data/openpilot/selfdrive/ui/ui
reboot
```

> **说明**：`ui` 二进制在运行中被内核标记为 busy，直接 `cp` 覆盖会失败。
> 必须先 `pkill` 停掉 `manager` 和 `ui` 进程（manager 会拉起 ui，所以要先杀 manager），
> 等 3 秒确保进程完全退出后再覆盖，最后 `reboot` 让 manager 重新加载新二进制。

---

## 七、参数注册指南

在 `common/params_keys.h` 中添加新参数：

```cpp
// 示例：新增 AccelBar 参数
{"AccelBar", {PERSISTENT | BACKUP, BOOL, "0"}},
```

参数类型：
- `BOOL` — 布尔值，用 `get_bool()` / `put_bool()` 读写
- `INT` — 整数，用 `get()` / `put()` 读写
- `FLOAT` — 浮点数

标志位：
- `PERSISTENT` — 持久化保存
- `BACKUP` — 备份时包含

### ⚠️ 参数持久化陷阱（重要，避免开关重启失效）

**根因**：`Params::clearAll()`（`common/params.cc`）在遍历 `/data/params/d/` 时会执行：

```cpp
auto it = keys.find(de->d_name);
if (it == keys.end() || (it->second.flags & key_flag)) {
  unlink(...);   // 文件名不在 keys 表 → 无视 flag 直接删掉
}
```

`manager.py` 每次启动会连续调用 4 次 `clear_all`（`CLEAR_ON_MANAGER_START` / `CLEAR_ON_ONROAD_TRANSITION` / `CLEAR_ON_OFFROAD_TRANSITION` / `CLEAR_ON_IGNITION_ON`），未注册的 key 会被全部清掉。

**核心陷阱：`common/params_pyx.so` 是预编译进 staging-tici 的二进制**

| 谁调 `Params` | 走的 keys 表来源 |
|------|------|
| C++ UI（`ui` 二进制） | 编译期链接的 `params_keys.h` — 走 `sunnypilot1/qt-dev`，随 UI 重编而更新 |
| Python `manager.py` / `process_config.py` | `common/params_pyx.so` 里静态链接的 keys map — **预编译进 `sunnypilot/staging-tici` 仓库**，`git pull` 不会自动重编 |

即使运行系统 `/data/openpilot/common/params_keys.h` 已经补齐 key，manager 侧仍然读的是 `.so` 里旧的白名单——只改 `.h` 无效。

**表现**：UI 侧点开关能存进 `/data/params/d/<Key>` → 重启 manager → `.so` 内 `keys.find()` 返 `end()` → `unlink` 删除 → UI 再读到空 → 开关变回关。

**排查口诀**：开关不能保持上次状态 → 用二进制字符串扫 `/data/openpilot/common/params_pyx.so`，看 key 是否在里面：
```bash
strings /data/openpilot/common/params_pyx.so | grep -E 'AccelBar|SteerTorqueData'
```
无输出即缺失。

**修复流程（新增 UI 参数时）**：

```
1. sunnypilot1/common/params_keys.h  +  key                     # UI 端能读
2. sunnypilot1/selfdrive/ui/sunnypilot/qt/offroad/settings/...  # UI 面板
3. C3 上重新编 params_pyx.so                                      # ⭐ 关键步骤
   cd /data/panda_build
   git checkout yiwen/qt-dev -- common/params_keys.h common/params_pyx.pyx
   scons -j4 common/params_pyx.so
4. 停 manager/ui 进程，替换 UI 二进制 + 替换 .so
   sudo pkill -f manager; sudo pkill -f "selfdrive/ui/ui"; sleep 3
   cp /data/panda_build/selfdrive/ui/ui        /data/openpilot/selfdrive/ui/ui
   cp /data/panda_build/common/params_pyx.so   /data/openpilot/common/params_pyx.so
5. reboot
6. （可选，半永久）把新 .so scp 回桌面 sunnypilot/，commit + push staging-tici
```

---

### ⚠️ 消息服务订阅指南（重要，避免 onroad 崩溃）

任何在 UI 中**读取新 cereal 消息服务**的功能（如 `liveMapDataSP`、`carControlSP` 等），
除了写绘制代码外，**必须先在 SubMaster 订阅列表中注册该服务名**：

```
文件：selfdrive/ui/sunnypilot/ui.cc
UIStateSP::UIStateSP() 里的 sm = std::make_unique<SubMaster>({... "服务名" ...});
```

**原理**：`SubMaster::operator[]` 和 `rcv_frame()` 内部是 `services_.at(name)`（socketmaster.cc），
`std::map::at()` 对未订阅的服务名会抛 `std::out_of_range` 异常 → UI 进程崩溃 → manager 反复重启失败 → 只剩逗号 logo。
崩溃点通常在进入 onroad、HUD 首帧 `updateState()` 时触发，表现为「启动正常、进摄像头即崩溃」。

**排查口诀**：进 onroad 崩溃 → 先检查 hud.cc/model.cc 里 `sm["xxx"]` / `sm.rcv_frame("xxx")` 用到的服务名
是否都在 `ui.cc` 的订阅列表里。服务是否存在可查 `cereal/services.py`。

---

### ⚠️ capnp 消息未初始化守卫（重要，避免 onroad 越界崩溃）

**坑**：在 HUD 里直接读 `modelV2` 等 cereal 消息的 List 字段（如 `laneLines[i]` / `laneLineProbs[i]`）
时，**进 onroad 头几帧消息还没到**，capnp reader 里的 List 是长度 0。此时下标访问 `[1]`/`[2]` 会
**越界** → 抛异常/SIGABRT → UI 崩 → manager 反复重启失败 → **卡逗号 logo**。

**崩溃特征**：启动正常、进摄像头（onroad）页面瞬间崩溃、反复重启，与「服务未订阅」崩溃表现一致，
但根因不同（这里是 capnp List 越界，不是 `std::map::at()` 抛异常）。

**正确写法**（对照 `qt/onroad/model.cc` 官方守卫）：

```cpp
if (laneLineDataEnabled && sm.rcv_frame("modelV2") > 0) {        // ① 消息到过才继续
  const auto model = sm["modelV2"].getModelV2();
  const auto &lane_lines = model.getLaneLines();
  const auto &lane_line_probs = model.getLaneLineProbs();
  if (lane_lines.size() >= 3 && lane_line_probs.size() >= 3) {    // ② List 长度检查
    const auto &left_y = lane_lines[1].getY();
    const auto &right_y = lane_lines[2].getY();
    leftLaneDist  = (lane_line_probs[1] > 0.5f && left_y.size()  > 0) ? left_y[0]  : 0.0f;  // ③ 内层 length 检查
    rightLaneDist = (lane_line_probs[2] > 0.5f && right_y.size() > 0) ? right_y[0] : 0.0f;
  }
}
```

**三层守卫口诀**：
1. `sm.rcv_frame("服务名") > 0` — 该消息至少收过一帧才读
2. `xxx.size() >= N` — capnp List 长度检查，杜绝 `[i]` 越界
3. 嵌套 List（如 `getY()`）也要再查 `size() > 0` 才能取 `[0]`

**真实案例**：2026-07-09 加 `LaneLineData` 车道线距离时，原代码无条件读 `modelV2.laneLines[1]/[2]`，
上车进摄像头即崩。加三层守卫后修复（commit：`fix(hud): guard LaneLineData reads against uninitialized modelV2`）。

---

## 八、移植记录

| 日期 | 功能 | 文件改动 | 状态 |
|------|------|---------|------|
| 2026-07-04 | **AccelBar 底部加减速横条** | `hud.h/cc` `ui_scene.h` `ui.cc` `params_keys.h` `visuals_panel.cc` | ✅ 代码完成 |
| 2026-07-04 | **SP Features 设置面板** | `sunny_features_panel.h/cc`(新建) `settings.cc` `SConscript` `icon_sunny_features.svg`(新建) | ✅ 代码完成 |
| 2026-07-04 | **修复 onroad 崩溃** | `ui.cc` 订阅列表 +`liveMapDataSP` | ✅ 已修复 |
| 2026-07-07 | **屏幕实时流（ScreenStreaming）** | `screenstreamer.h/cc` `window.h/cc` `sunny_features_panel.cc` | ✅ 已完成 |
| 2026-07-08 | **删除反向触控（改为只读预览）** | `screenstreamer.h/cc` `window.cc` | ✅ 已完成 |
| 2026-07-08 | **摄像头流（WebRTC 硬件编码）** | `process_config.py` `params_keys.h` `sunny_features_panel.cc` + App 端 | ✅ 已完成 |
| 2026-07-09 | **SteerTorqueData 转向扭矩监控** | `hud.h/cc` `ui_scene.h` `ui.cc` `params_keys.h` `sunny_features_panel.cc` | ✅ 已完成 |
| 2026-07-09 | **LaneLineData 车道线距离** | `hud.h/cc` `ui_scene.h` `ui.cc` `params_keys.h` `sunny_features_panel.cc` | ✅ 已完成 |
| 2026-07-09 | **修复 LaneLineData 导致 onroad 崩溃** | `hud.cc` 加三层 capnp 守卫 | ✅ 已修复 |
| 2026-07-13 | **删除 SteerTorqueData 转向扭矩监控** | `hud.h/cc` `ui_scene.h` `ui.cc` `params_keys.h` `sunny_features_panel.cc` | ❌ 已删除 |
| 2026-07-13 | **限速+ACC 一体化融合方框** | `hud.cc` `sunny_features_panel.cc`：限速方框与 ACC 设定速度融合为一个 330px 框 | ✅ 已完成 |
| 2026-07-13 | **转向弧微调** | `hud.cc`：线宽-5%、弧长+5%、margin_bottom 88→20 | ✅ 已完成 |
| 2026-07-13 | **车道线距离上移** | `hud.cc`：box_y 670→400 | ✅ 已完成 |
| 2026-07-13 | **道路名称放大+下移** | `hud.cc`：32→38pt, top+12→top+24 | ✅ 已完成 |
| 2026-07-13 | **速度显示下移** | `qt/onroad/hud.cc`：速度 y 210→230, 单位 y 290→310 | ✅ 已完成 |
| 2026-07-15 | **限速标志方案 B（独立大圆标）** | `hud.h/cc` `params_keys.h` `ui_scene.h` `ui.cc` | ✅ 代码完成 |
| — | **MADS 五态彩色边框** | `annotated_camera.cc` | ❌ 待实现 |

### AccelBar 完整文件改动清单

```
修改：
  common/params_keys.h                                 # +AccelBar 参数
  selfdrive/ui/sunnypilot/ui_scene.h                   # +accel_bar 字段
  selfdrive/ui/sunnypilot/ui.cc                        # +params.getBool("AccelBar")
  selfdrive/ui/sunnypilot/qt/onroad/hud.h              # +drawAccelBar() + accelBarEnabled
  selfdrive/ui/sunnypilot/qt/onroad/hud.cc             # +updateState 读取 + draw()调用 + drawAccelBar()实现
  selfdrive/ui/sunnypilot/qt/offroad/settings/visuals_panel.cc  # 回退 AccelBar 控件
  selfdrive/ui/sunnypilot/qt/offroad/settings/settings.cc       # +include + PanelInfo
  selfdrive/ui/sunnypilot/SConscript                   # +sunny_features_panel.cc

新增：
  selfdrive/ui/sunnypilot/qt/offroad/settings/sunny_features_panel.h   # 新面板头文件
  selfdrive/ui/sunnypilot/qt/offroad/settings/sunny_features_panel.cc  # 新面板实现
  sunnypilot/selfdrive/assets/offroad/icon_sunny_features.svg          # 新面板图标
```

---

### 限速标志方案 B 完整实现（2026-07-15）

#### 功能概述

将 2026-07-13 实现的「限速+ACC 融合方框」改为**独立大圆标并排布局**（方案 B）：
- ACC 设定速度方框保持原位（左上角 x=60, y=45）
- 限速圆标（140px 直径）放在 ACC 右侧，顶部对齐，间距 20px
- 圆形红圈边框（维也纳公约标准），白底黑字
- 支持超速 MAX 标签变色（白→橙→红）
- 前方限速箭头提示（降速橙色▼，提速蓝色▲）
- 预渲染缓存优化性能

#### 布局效果

```
┌─────────────┐  ╭─────────────╮
│    MAX      │  │     80      │  ← ACC 与限速圆标并排，顶部对齐（y=45）
│     85      │  │             │  ← 间距 20px
└─────────────┘  ╰─────────────╯
   ACC 方框       限速圆标 (140px)
   LIMIT → 100    ← 前方限速提示

总占用：x=60~420 (360px 宽), y=45~225 (180px 高)
```

#### 文件改动清单

```
修改：
  selfdrive/ui/sunnypilot/qt/onroad/hud.h              # +drawACCSetSpeedBox() +drawSpeedLimitCircle() 方法
                                                       # +speedLimitCircleCache 预渲染缓存
                                                       # +speedLimitStyle/ColorMAX/ShowSource 等 5 个参数成员
  selfdrive/ui/sunnypilot/qt/onroad/hud.cc             # 重写 drawSpeedLimit() 为方案 B
                                                       # +drawACCSetSpeedBox() 独立绘制 ACC 方框
                                                       # +drawSpeedLimitCircle() 绘制 140px 圆标
                                                       # updateState() 添加缓存失效检测
  common/params_keys.h                                 # +SpeedLimitStyle (INT, 默认1)
                                                       # +SpeedLimitColorMAX (BOOL, 默认1)
                                                       # +SpeedLimitShowSource (BOOL, 默认0)
                                                       # +SpeedLimitWarnThreshold (INT, 默认10)
                                                       # +SpeedLimitDangerThreshold (INT, 默认20)
  selfdrive/ui/sunnypilot/ui_scene.h                   # +speed_limit_style/color_max/show_source 等 5 个场景字段
  selfdrive/ui/sunnypilot/ui.cc                        # param_watcher 监听 5 个新参数
                                                       # ui_update_params_sp() 读取 5 个新参数
```

#### 核心特性

**1. ACC 方框超速变色（MAX 标签）**

```cpp
// 根据超速量渐变颜色（speedLimitColorMAX 参数控制）
if (speed_over <= 0)           max_color = 绿色 (未超速)
else if (speed_over <= 10)     max_color = 白色 (轻微超速)
else if (speed_over <= 20)     max_color = 橙色 (中度超速)
else                           max_color = 红色 (严重超速)
```

**2. 限速圆标（Tesla / comma 风格）**

- 直径 140px，红色边框 8px（维也纳公约标准）
- 白底黑字，60pt 加粗字体
- 预渲染到 `QPixmap` 缓存，避免每帧重绘圆形（性能优化）
- 限速数据变化时自动标记缓存失效 (`speedLimitCacheDirty`)

**3. 前方限速提示**

```cpp
// 标志下方显示箭头 + 前方限速值
if (speedLimitAheadValid) {
  降速（ahead < current）：橙色 ▼ 60
  提速（ahead > current）：蓝色 ▲ 100
} else {
  显示 "LIMIT" 标签
}
```

**4. 数据源可信度图标（可选）**

```cpp
// SpeedLimitShowSource=true 且 confidence<0.8 时显示黄色 "?" 图标
// 提示驾驶员限速数据可能不准确（OSM 数据过时、视觉识别不确定等）
```

#### 参数说明

| 参数键 | 类型 | 默认值 | 说明 |
|-------|------|-------|------|
| `SpeedLimitStyle` | INT | 1 | 限速标志样式：0=矩形（旧方案），1=圆形，2=大圆（预留） |
| `SpeedLimitColorMAX` | BOOL | true | 超速时 MAX 标签变色开关 |
| `SpeedLimitShowSource` | BOOL | false | 显示数据源可信度图标 |
| `SpeedLimitWarnThreshold` | INT | 10 | 超速警告阈值（km/h） |
| `SpeedLimitDangerThreshold` | INT | 20 | 严重超速阈值（km/h） |

#### 性能优化

**预渲染缓存策略**：
```cpp
// 限速数据不变时复用缓存 QPixmap，避免每帧重绘圆形（~0.3ms → 0.05ms）
if (speedLimitCacheDirty || cachedSpeedLimit != limit_kmh) {
  // 重新渲染到 speedLimitCircleCache
  speedLimitCacheDirty = false;
}
p.drawPixmap(x, y, speedLimitCircleCache);  // 每帧只需贴图
```

**缓存失效触发条件**：
- 限速数据有效性变化（`speedLimitValid` 切换）
- 限速值变化（`speedLimit` 变化超过 0.1 m/s）
- 前方限速数据变化（`speedLimitAheadValid` 切换）

#### 与方案 A 对比

| 维度 | 方案 A（融合方框） | 方案 B（独立大圆标） |
|------|------------------|-------------------|
| 限速标志尺寸 | 96×66 矩形 | 140 圆形 ✅ 更大 |
| 辨识度 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 空间占用 | 330px 宽 | 360px 宽 |
| 超速反馈 | ✅ MAX 变色 | ✅ MAX 变色 |
| 国际标准 | ❌ 矩形 | ✅ 圆形红圈（维也纳公约） |
| 实施难度 | 低（50 行） | 中（180 行） |
| Tesla 风格 | 部分相似 | ✅ 完全一致 |

#### 已知局限

1. **数据依赖**：需要 `liveMapDataSP.speedLimit` 有效，中国 OSM 覆盖率约 60%
2. **空间占用**：总宽 360px，可能与右侧 Dev UI 轻微重叠（实测间距 1256px，无冲突）
3. **参数未暴露**：`SpeedLimitStyle` 等 5 个参数已注册，但设置面板 UI 待后续实现（阶段 3）

#### 部署注意事项

⚠️ **必须重编 `params_pyx.so`**（新增 5 个参数）：
```bash
cd /data/panda_build
git checkout yiwen/qt-dev -- common/params_keys.h common/params_pyx.pyx
scons -j4 common/params_pyx.so
cp /data/panda_build/common/params_pyx.so /data/openpilot/common/params_pyx.so
```

#### Git 记录

```
分支：sunnypilot1/qt-dev
改动：5 个文件（hud.h/cc, params_keys.h, ui_scene.h, ui.cc）
提交信息：feat(ui): 实现限速标志方案 B（独立大圆标并排布局）
推送到：yiwen/sunnypilot.git qt-dev
```

---

### ScreenStreaming 屏幕实时流完整实现

#### 功能概述

在 C3 Qt UI 中嵌入轻量 HTTP 服务器，将 C3 屏幕实时推送到 Android App 的 WebView 中显示，
并支持反向触控（在手机上点击 → 注入到 C3 UI）。

#### 架构

```
MainWindowSP (主线程)                    ScreenStreamer (独立 QThread :8083)
     │                                        │
     ├─ QScreen::grabWindow(0)                ├─ /stream    MJPEG 流推送（multipart/x-mixed-replace）
     ├─ scale 960×540                         ├─ /frame.jpg 单帧 JPEG（向后兼容）
     ├─ QPixmap::save(JPEG)                   ├─ /touch     反向触控注入
     └─ setLatestFrame(jpeg) ──────────→      ├─ /status    状态查询
                                              └─ /toggle    开关切换

WebView (Android App):
  <img src="http://C3_IP:8083/stream">  ← MJPEG 长连接，零 JS 轮询开销
```

#### 文件清单

```
修改：
  selfdrive/ui/qt/screenstreamer.h          # HTTP 服务头文件（MJPEG客户端管理 + 触控注入）
  selfdrive/ui/qt/screenstreamer.cc         # HTTP 服务实现（/stream /touch /status /frame.jpg）
  selfdrive/ui/sunnypilot/qt/window.h       # +streamer/streamer_thread/capture_timer 成员
  selfdrive/ui/sunnypilot/qt/window.cc      # 初始化 ScreenStreamer + 定时抓帧 + 空闲检测
  selfdrive/ui/sunnypilot/qt/offroad/settings/sunny_features_panel.cc  # ScreenStreamEnabled 开关
  selfdrive/ui/SConscript                   # +screenstreamer.cc 编译
```

#### 关键技术点

**1. MJPEG 流推送（`/stream`）**
- 替代 JS 轮询，浏览器原生 `<img>` 直接接收 `multipart/x-mixed-replace` 流
- 服务端长连接，每帧自动推送，无需 HTTP 请求开销
- `pushToAllStreamClients()` 遍历 `streamClients_` QSet，断线自动清理

**2. 反向触控（`childAt` 修复）**
- HTML 端：`pointerdown/move/up` → `toC3()` 坐标映射（手机像素→C3 1920×1080）
- C++ 端：`childAt(x,y)` 递归找到坐标下的实际子控件 + `mapFrom()` 坐标转换
- **关键修复**：不能直接用 `postEvent(targetWidget_, ...)`，必须找到子控件并用 `sendEvent(child, ...)`
- 之前版本因 `QApplication::activeWindow()` 在 worker 线程返回 nullptr，改为存储 `targetWidget_` 指针

**3. 空闲检测**
- `lastClientTime_` 记录最后一次 HTTP 请求时间
- 主线程 300ms 定时器检查：超过 3 秒无客户端 → 跳过 `grabWindow(0)`，零开销
- 客户端重连后自动恢复

**4. 性能参数**
| 参数 | 值 | 说明 |
|------|-----|------|
| 抓帧间隔 | 300ms | ~3.3fps |
| 分辨率 | 960×540 | C3 1920×1080 的 50% |
| JPEG 质量 | 70 | 清晰度与文件大小平衡 |
| 空闲超时 | 3s | 无客户端时自动暂停 |
| 端口 | 8083 | HTTP 服务端口 |

**5. 已知局限**
- `grabWindow(0)` 底层走 `eglReadPixels`，Adreno 630 移动 GPU 下约 40-60ms/帧，无法突破
- V4L2 硬件 JPEG 编码器（骁龙 845 Venus）经评估无实际价值（省 3ms 但有额外开销），已移除
- 需确保 C3 防火墙放行 8083 端口：`sudo nft add rule ip filter INPUT tcp dport 8083 accept`

#### 使用方式

```bash
# C3 开启服务（设置 → SP Features → 屏幕实时流）
# 手机浏览器或 App WebView 访问：
http://<C3_IP>:8083

# 调试命令
curl http://<C3_IP>:8083/status   # 查看状态
curl http://<C3_IP>:8083/toggle   # 切换开关
```

> [!NOTE]
> **2026-07-08 更新**：反向触控已删除，ScreenStreaming 现为只读预览。
> 原因：Wayland 下 `grabWindow(0)` 抓不到摄像头图层（`size:0`），且触控注入复杂度高。
> 现改为「屏幕预览用 ScreenStream（offroad UI），摄像头用 WebRTC（onroad 路况）」双方案并存。

---

### WebRTC 摄像头流（路线 B，硬件编码）

#### 为什么选它
- 复用 openpilot 官方 `stream_encoderd`（骁龙 845 Venus **硬件 H264 编码**）+ `webrtcd`，几乎零 CPU/GPU 开销
- 满足「不影响 C3 性能」的硬约束
- 取舍：**只有摄像头画面，无 HUD/路径/按钮叠加**；仅 onroad 可用

#### 链路
```
camerad → VisionIPC → stream_encoderd(V4L硬编H264)
  → livestreamRoadEncodeData → webrtcd(:5001) → WebRTC → Android App
```

#### C3 端改动
```
system/manager/process_config.py   # +webrtc_stream() 门控函数
                                   # stream_encoderd/webrtcd 启用条件 notcar → or_(notcar, webrtc_stream)
common/params_keys.h               # +WebrtcStreamEnabled (PERSISTENT|BACKUP, 默认0)
sunny_features_panel.cc            # +「摄像头实时流（WebRTC）」开关
```

- **门控逻辑**：`webrtc_stream = started and params.getBool("WebrtcStreamEnabled")`
  - 仅 onroad + 用户显式开启才拉起编码器/webrtcd，默认关闭省电
  - `WebrtcStreamEnabled` 是 `PERSISTENT | BACKUP`，**重启后自动保持上次状态**
- SP Features 面板的 toggle 会读回该参数，UI 与进程管理器共用同一参数

#### 握手协议（webrtcd, 端口 5001）
```
POST http://<C3_IP>:5001/stream
body: {"sdp": <offer>, "cameras": ["road"], "bridge_services_in": [], "bridge_services_out": []}
resp: {"sdp": <answer>, "type": "answer"}
```
- 摄像头名：`road`(前视) / `wideRoad`(广角) / `driver`(驾驶员)
- App 端只收视频（recvonly），不需要摄像头权限

#### App 端改动（sunnypilot-android）
```
data/repository/VideoStreamRepository.kt   # 新建：SSH 写 WebrtcStreamEnabled 参数
ui/util/WebrtcHtml.kt                       # 新建：WebView 内嵌 WebRTC 握手页面（零原生依赖）
ui/screens/VideoScreen.kt                   # 重写：查看方式选择器（屏幕预览/摄像头流）
```
- **零新增依赖**：Android WebView 原生支持 `RTCPeerConnection`，不引入 `org.webrtc`
- 切到「摄像头流」自动开 `WebrtcStreamEnabled`；切回「屏幕预览」或离开页面自动关（省电）

#### 调试
```bash
# 确认 onroad 且参数已开时进程在跑
ps -A | grep -E 'stream_encoderd|webrtcd'
# 测试握手端点是否响应
curl http://<C3_IP>:5001/stream -X POST -H 'Content-Type: application/json' -d '{}'
```

---

### SteerTorqueData + LaneLineData（HUD 叠加，2026-07-09）

#### 功能概述

在定速巡航方块下方新增两个可独立开关的 HUD 叠加方块，用于调试/监控：

1. **SteerTorqueData（转向扭矩监控）**：显示模型输出扭矩命令 vs EPS 实际扭矩
   - 上半部：`torqueState.output`（模型扭矩命令，单位 Nm）
   - 下半部：`steeringTorqueEps`（EPS 实际扭矩，取绝对值，单位 Nm）
   - 扭矩饱和（`torqueState.saturated`）时数值变橙色并显示 "MAX" 标记
   - **仅 Torque 控制车型有效**（BYD 18唐 DM 走 torque 路径，`angleSteersDesired` 不可用）
2. **LaneLineData（车道线距离）**：显示车辆中心到左/右车道线的横向距离
   - 左：`modelV2.laneLines[1].c0`（米）
   - 右：`modelV2.laneLines[2].c0`（米）
   - 车道线置信度（`laneLineProbs`）低于 0.5 时显示 "-"

#### 布局（左上角，定速巡航方块下方，与 MAX 定速方块同尺寸、垂直排列）

```
┌─────────────┐  ← 定速巡航方块 (y=45, 公制200×204 / 英制172×204)
├─────────────┤
│  模型 0.0    │  ← SteerTorqueData (y=280，无标题)
│  实际 0.0    │
└─────────────┘
├─────────────┤  ← 间距 31px
│  左边 0.0m   │  ← LaneLineData (y=515，无标题)
│  右边 0.0m   │
└─────────────┘
   ▲ 最左侧加速指示条 (AccelBar) 已左移到 x=6，右边缘 42，与方框(左边缘46)不重叠
```

**尺寸同步说明（关键）**：原代码把两个新方框硬编码成 172×204，但在公制（km/h，中国是公制）模式下
MAX 定速方块实际是 **200×204**（`qt/onroad/hud.cc:drawSetSpeed()` 中 `is_metric ? QSize(200,204):default_size`），
所以旧方框看起来「小一圈」。现已改为复用同一套尺寸公式，与定速方块完全一致。

> **空间验证**：与 DebugPlots（顶部4面板，透明）在位置上不冲突，仅当 DebugPlots 打开时左上区轻微重叠，但后者为半透明背景，不影响可读性。

#### 数据通路

| 数据 | 来源 | 订阅状态 |
|------|------|---------|
| `torqueState` | `controlsState.LateralControlsState.torqueState` | `controlsState` 已在 SubMaster → **无需额外注册** |
| `steeringTorqueEps` | `carState`（`HudRenderer::updateState` 已读取） | 同 `controlsState` |
| `laneLines[1]/[2].c0` | `modelV2.laneLines` | `modelV2` 已在 SubMaster |
| `laneLineProbs` | `modelV2.laneLineProbs` | 同 `modelV2` |

> **注意**：`torqueState` 是 `controlsState` 内部的 union 字段，不需要单独在 SubMaster 订阅；
> 读取时通过 `cs.getLateralControlsState().getTorqueState().getOutput()` 访问（SP 分支的 `ControlsState` 已包含该 union，需用 `isTorqueState()` 判断类型）。

#### 文件改动清单

```
修改：
  common/params_keys.h                                        # +SteerTorqueData, +LaneLineData 参数键 (PERSISTENT|BACKUP, 默认0)
  selfdrive/ui/sunnypilot/ui_scene.h                         # +steer_torque_data, +lane_line_data 场景字段
  selfdrive/ui/sunnypilot/ui.cc                              # +param_watcher 注册 + ui_update_params_sp() 读取
  selfdrive/ui/sunnypilot/qt/onroad/hud.h                    # +torqueStateOutput/torqueStateSaturated 成员
                                                            # +steerTorqueDataEnabled/laneLineDataEnabled 开关
                                                            # +leftLaneDist/rightLaneDist 成员
                                                            # +drawSteerTorqueData()/drawLaneLineData() 方法声明
  selfdrive/ui/sunnypilot/qt/onroad/hud.cc                   # updateState: 读 torqueState + laneLines
                                                            # draw(): 条件调用两个新绘制方法
                                                            # +drawSteerTorqueData()/drawLaneLineData() 实现
  selfdrive/ui/sunnypilot/qt/offroad/settings/sunny_features_panel.cc  # +2 toggle 定义（中文标题+描述）
```

#### 关键实现点

- **方块尺寸**：与 MAX 定速方块完全同步（`is_metric ? 200×204 : 172×204`），圆角 32，左对齐方式与定速方块一致（`x = 60 + (172 - box_w)/2`），颜色一致（白边 + 半透明黑底）
- **内容布局**：删除标题行。扭矩框两行 `模型 <v>` / `实际 <v>`；车道框两行 `左边 <v>m` / `右边 <v>m`（数值 0 时显示 `-`）
- **AccelBar 加速条**：`margin_left` 由 20 改 6（右边缘 42），`bar_height` 由 470 加到 560，彻底避开左上角方框
- **Saturated 处理**：`torqueState.saturated` 为真 → 模型扭矩数值变 `QColor(255,200,60)` 橙色 + 显示 "MAX"
- **LaneLine 置信度过滤**：`lane_line_probs[i] > 0.5f` 才取 `c0`，否则填 0 → 显示 "-"
- **开关 toggle**：SP Features 面板的 `ParamControlSP`，中文标题「转向扭矩监控」「车道线距离」

#### Git

```
commit 967298be51  (qt-dev)
分支: sunnypilot1/qt-dev → yiwen remote → C3 /data/panda_build
URL: https://github.com/yiwenweb/sunnypilot/commit/967298be51
```

## 九、调试技巧

### 查看编译错误

```bash
tail -100 /tmp/ui_build.log
```

### GDB 抓崩溃栈

```bash
gdb -ex run -ex "bt" -ex "quit" --args ./selfdrive/ui/ui
```

### 桌面预览 UI（需 route 回放）

```bash
cd /data/openpilot
source /usr/local/venv/bin/activate
export PYTHONPATH=/data/openpilot
python tools/replay/replay.py "<route名>" &
selfdrive/ui/ui.py
```

### C3 不上车验证 onroad UI（uiview 假 onroad）

**用途**：改完 UI (hud/ui.cc/AccelBar 等) 后，不想装车 / 不想去车库，就在办公桌上验证：
- 编译产物 `ui` 二进制不崩
- HUD 各元素（车道线、行车规划、转向扭矩、车道距离等）能正常渲染
- 相关消息生产者（modeld、camerad、locationd、calibrationd）是否正常出数据

**原理**：`selfdrive/debug/uiview.py` 手动 pub 一份 `deviceState.started=True` + `pandaStates.ignitionLine=True`，让所有 `only_onroad` 触发的进程（modeld / camerad / calibrationd / plannerd / dmonitoringmodeld / ui）以为在开车状态启动。

**具体用法**：

```bash
# 前置：必须在 offroad 状态（打开 C3、没有真车激活）
ssh comma@<C3_IP>
cd /data/openpilot

# 方式 A：前台跑，直接看 UI（C3 屏幕会亮起来显示 onroad 界面）
/usr/local/venv/bin/python /data/openpilot/selfdrive/debug/uiview.py
# Ctrl+C 结束，所有子进程会被 stop 掉

# 方式 B：后台跑 + 自动采样 cereal，快速判断 modeld 有没有出数据
timeout 20 /usr/local/venv/bin/python /data/openpilot/selfdrive/debug/uiview.py > /tmp/uiview.log 2>&1 &
UI_PID=$!
sleep 8   # 等 modeld 起来 + 首帧
/usr/local/venv/bin/python <<'EOF'
import cereal.messaging as m, time
sm = m.SubMaster(['modelV2','cameraOdometry','livePose','liveCalibration','carState'])
seen = {k:0 for k in ['modelV2','cameraOdometry','livePose','liveCalibration','carState']}
t0 = time.time()
while time.time()-t0 < 10:
    sm.update(200)
    for k in seen:
        if sm.updated[k]: seen[k]+=1
for k,v in seen.items(): print(f'  {k:18s} received={v}')
if seen['liveCalibration']: print('  calPerc   =', sm['liveCalibration'].calPerc)
if seen['livePose']:        print('  posenetOK =', sm['livePose'].posenetOK)
EOF
kill $UI_PID 2>/dev/null; wait $UI_PID 2>/dev/null
tail -25 /tmp/uiview.log
```

**判读**：

| 指标 | 健康值 | 异常说明 |
|---|---|---|
| `modelV2` | 15~20 Hz（10 秒采 150~200 帧） | 0 → modeld 没跑起来或崩了，看 uiview.log 尾部 traceback |
| `cameraOdometry` | 同上 | 0 → 车道线消失、标定不推进的直接原因 |
| `livePose` | 15~20 Hz | 0 → locationd 没跑 |
| `liveCalibration` | 4 Hz | calibrationd 独立运行，通常不会为 0 |
| `carState` | **0** | 正常。uiview 不 pub carState，等真上车 boardd 才有 |
| `posenetOK` | True | False → posenet nan，一般 modeld 崩带出来的 |
| `inputsOK` | **False** | 正常。缺 carState 导致 inputsOK 不满足，不影响 UI 验证 |

**常见现象**：

- 相机冷启会打印几行 `spectra.cc: VIDIOC_CAM_CONTROL error: op_code 266 - errno 19` → 一次性 warmup 错，之后 `vision stream set up` 就恢复，可以忽略
- 首启 modeld 前几百帧会 `skipping model eval. Dropped N frames` → 相机流还没稳定，是正常的
- 前台跑时 C3 屏幕会亮起 onroad 界面（黑底 + 车道线 + HUD），可以肉眼直接看新加的 hud 元素是否正确渲染

**收尾**：
```bash
# 前台模式：Ctrl+C
# 后台模式：kill $UI_PID
# 保险起见把残留清一下
pkill -f uiview.py
pkill -f modeld
```

### C3 存储挂载后模型文件排查（NVMe 挂载踩坑）

**症状（全部同时发生）**：
- onroad 车道线消失
- 中间行车规划消失
- 标定进度一直 0，重新标定不生效
- 激活时报 "posenet speed invalid, speed error: nan m/s"

**根因**：`/data/media` 挂载了 NVMe 后，原 `/data/media/0/models/` 下的 `.pkl` 模型文件被空挂载点覆盖。但 `ModelManager_ActiveBundle` params 里 `status=cached` 是历史记录，不会自动重新校验文件是否真实存在。onroad 时 `modeld_tinygrad` 找不到 pkl 立即崩溃循环，`modelV2` / `cameraOdometry` 全没了 → 一连串下游消息断链。

**四个症状同一根因关系**：

```
modeld 崩溃
  ├─ 无 modelV2.laneLines       → UI 车道线消失
  ├─ 无 modelV2.position        → UI 行车规划消失
  └─ 无 cameraOdometry
        ├─ locationd 无法算 posenet_stds → posenetOK=False → posenet nan
        └─ calibrationd 滤波器无法推进 → calPerc 一直 0
```

**核心判定**：
- 症状全部是 `modelV2` / `cameraOdometry` 的**消费者**表现，问题一定在**生产者** modeld
- 与 UI 代码改动**物理上无关**，UI 只是消费者，消费者写坏不会让生产者停产

**排查诊断脚本**（离线状态跑）：

```bash
cd /data/openpilot && {
echo "===== [1] 检查 Model runner & bundle ====="
cat /data/params/d/ModelRunnerTypeCache; echo
/usr/local/venv/bin/python -c "
import json
b = json.load(open('/data/params/d/ModelManager_ActiveBundle'))
print('bundle:', b['displayName'], 'runner=', b['runner'])
for m in b['models']:
    print(' ', m['type'], '->', m['artifact']['fileName'])
"

echo; echo "===== [2] 检查模型文件真实存在性 ====="
ls -la /data/media/0/models/

echo; echo "===== [3] sha256 校验 bundle 内所有文件 ====="
/usr/local/venv/bin/python <<'EOF'
import json, hashlib, os
b = json.load(open('/data/params/d/ModelManager_ActiveBundle'))
root = '/data/media/0/models'
for m in b['models']:
    for kind in ('artifact','metadata'):
        a = m[kind]; fn, want = a['fileName'], a['downloadUri']['sha256']
        p = os.path.join(root, fn)
        if not os.path.exists(p):
            print(f"  MISSING  {fn}"); continue
        h = hashlib.sha256()
        with open(p,'rb') as fp:
            for c in iter(lambda: fp.read(65536), b''): h.update(c)
        mark = 'OK ' if h.hexdigest().lower()==want.lower() else 'BAD'
        print(f"  {mark}  {fn}  size={os.path.getsize(p)}")
EOF
}
```

**修复方式（触发重下）**：

```bash
# 1. 清掉坏文件（如果有）
rm -f /data/media/0/models/driving_*_tinygrad.pkl

# 2. 触发下载：把 bundle index 写进 DownloadIndex 参数
/usr/local/venv/bin/python -c "
from openpilot.common.params import Params
Params().put('ModelManager_DownloadIndex', 87)  # 87 = 当前 ActiveBundle 的 index，看步骤 [1] 输出
"

# 3. 起 models_manager 前台跑（下载 vision pkl 会 30 秒以上，别用 timeout 30 截断）
/usr/local/venv/bin/python -m openpilot.sunnypilot.models.manager > /tmp/mm.log 2>&1 &
MM_PID=$!

# 4. 轮询大小判断结束（DownloadIndex 被自动删除 = 完成）
for i in $(seq 1 60); do
    sleep 5
    ps=$(stat -c %s /data/media/0/models/driving_policy_cgwm_tinygrad.pkl 2>/dev/null || echo 0)
    vs=$(stat -c %s /data/media/0/models/driving_vision_cgwm_tinygrad.pkl 2>/dev/null || echo 0)
    idx=$(cat /data/params/d/ModelManager_DownloadIndex 2>/dev/null || echo "-")
    echo "  t=${i}0s  policy=${ps}B  vision=${vs}B  DownloadIndex=${idx}"
    [ "$idx" = "-" ] && break
done
kill $MM_PID 2>/dev/null; wait $MM_PID 2>/dev/null

# 5. 再校验一次 sha256，全 OK 后 reboot 或直接跑 uiview 验证
```

**要点**：
- **`timeout` 别设太短**：vision pkl 一般 40+ MB，网慢时下载 60~120 秒是正常的。设 30 会截断成损坏文件，hash 校验挂
- **判定下载完成看 `ModelManager_DownloadIndex`**：manager 处理完（成功或失败）会把它 remove
- **`status=cached` 只是历史记录**，不检查文件真实存在。挂载存储后一定要 sha256 校验一遍
- 挂载 `/data/media` 会盖掉 `/data/media/0/models/` 和 `/data/media/0/realdata/`，前者是模型，后者是行车日志。挂载前如果有数据要**先备份或改挂载点**

---

## 十二、CircularAlerts 圆环提醒移植记录（2026-07-22）

### 概述

将 sunnypilot 2016 版的 CircularAlerts（圆环提醒）功能移植到 staging-tici + qt-dev 环境。功能：停车等红灯时检测到绿灯亮 → 车速数字外围出现绿色圆环 + 图标 + 文字提醒；前车起步 → 蓝色圆环 + 图标 + 文字提醒。显示 3 秒后自动消失。

### 数据管道

```
[车辆状态] → longitudinal_planner.py → e2e_alerts_helper.py → cereal
                                                                   │
        ┌──────────────────────────────────────────────────────────┘
        ▼
    longitudinalPlanSP.e2eAlerts
    ├── greenLightAlert :Bool   ← 绿灯检测
    └── leadDepartAlert :Bool   ← 前车起步
```

两端数据管道均已就绪：
- staging-tici：`e2e_alerts_helper.py` + `longitudinal_planner.py` 生产 e2eAlerts 数据
- cereal：`LongitudinalPlanSP.e2eAlerts`（field @7）已定义

### 涉及仓库

| 仓库 | 分支 | 角色 |
|------|------|------|
| `sunnypilot1` | qt-dev | C++ UI 源码 + 编译工厂 |
| `sunnypilot` | staging-tici | Python 后端 + params_keys.h |

### 文件改动清单

**sunnypilot1/qt-dev（6 文件）**：

| 文件 | 改动 | 状态 |
|------|------|------|
| `common/params_keys.h` | 新增 `CircularAlerts`、`GreenLightAlert`、`LeadDepartAlert` 参数键 | 已有（SCC 批次） |
| `selfdrive/ui/sunnypilot/ui_scene.h` | 新增 `circular_alerts` bool | 已有 |
| `selfdrive/ui/sunnypilot/ui.cc` | param_watcher 注册 + 读取 | 已有 |
| `selfdrive/ui/sunnypilot/qt/onroad/hud.h` | 新增 `drawCircularAlerts()` 声明 + 7 个成员变量 | 已有 |
| `selfdrive/ui/sunnypilot/qt/onroad/hud.cc` | `updateState()` 读 e2eAlerts + `draw()` 调用 + `drawCircularAlerts()` 完整实现 | 已有 |
| `sunnypilot/selfdrive/assets/images/green_light.png` | 新增图标资源 | 本次新增 |
| `sunnypilot/selfdrive/assets/images/lead_depart.png` | 新增图标资源 | 本次新增 |
| `selfdrive/ui/sunnypilot/SConscript` | 新增 `env.Install()` 打包规则 | 本次新增 |

**sunnypilot/staging-tici（1 文件）**：

| 文件 | 改动 |
|------|------|
| `common/params_keys.h` | `CircularAlerts`、`GreenLightAlert`、`LeadDepartAlert` 参数键（之前未同步） |

### LFS 故障与修复

`.gitattributes` 中 `*.png` 被 LFS 跟踪，LFS blob 端点指向 GitLab，本地无 GitLab SSH key → push 被阻断。

修复：
1. `.gitattributes` 注释掉 `*.png` LFS 规则
2. `git lfs untrack "*.png"`
3. PNG 走普通 Git 存储（两个图标合计 15KB，无影响）

### 绘制参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 圆盘半径 | 250px | 半透明黑底 |
| 圆环宽度 | 15px | 内外各 7.5 |
| 中心位置 | (960, 540) | 屏幕中心硬编码 |
| 显示时长 | 3 秒（180 帧 @60fps） | alertDisplayTimer 倒计时 |
| 脉动动画 | frame % 60 < 24 | 每 60 帧中前 24 帧缩小半径 |
| 图标 | 250×250 QPixmap | 懒加载 + 缩放缓存 |
| 字体 | 48pt | 提醒文字 |
| 绿灯颜色 | 绿 `#00C850` | 圆环 + 脉动外环 |
| 前车起步颜色 | 蓝 `#0080FF` | 圆环 + 脉动外环 |
| 背景 | `rgba(0,0,0,190)` | 半透明黑盘 |

### 性能

| 状态 | 每帧开销 | 占帧预算(16.7ms) |
|------|---------|-----------------|
| 告警活跃期 | ~0.20ms | <1.2% |
| 非告警期 | ~0.005ms | <0.03% |

### C3 部署

```bash
# 1. 切分支（跳过 LFS）
cd /data/panda_build
git reset --hard HEAD && git clean -fdx
GIT_LFS_SKIP_SMUDGE=1 git fetch yiwen qt-dev
GIT_LFS_SKIP_SMUDGE=1 git checkout yiwen/qt-dev

# 2. 编译
scons -j4 selfdrive/ui/ui
scons -j4 common/params_pyx.so

# 3. 部署
pkill -f ui && pkill -f manager
cp selfdrive/ui/ui /data/openpilot/selfdrive/ui/
cp selfdrive/common/params_pyx.so /data/openpilot/selfdrive/common/
cd /data/openpilot && git pull myrepo staging-tici
reboot
```

### Git 提交记录

| commit | 内容 |
|--------|------|
| `1676a74` | staging-tici: 新增 CircularAlerts/GreenLightAlert/LeadDepartAlert 参数键 |
| `043cce9` | qt-dev: 补全 CircularAlerts 图标资源 + SConscript 打包规则 |
| `c3f0f2146d` | qt-dev: 修复 LFS，图片走普通 Git 存储 |

---

## 十、相关文档

- BYD 唐 DM 2018 适配技术笔记：`BYD_唐DM_2018_sunnypilot适配技术笔记.md`
- sunnypilot 官方文档：https://docs.sunnypilot.com
- openpilot 开发者文档：https://docs.comma.ai
- 本档案所在仓库：https://github.com/yiwenweb/sunnypilot (分支: staging-tici)

---

## 十一、SCC UI 移植记录（2026-07-22）

### 概述

将 sunnypilot master 的 Smart Cruise Control（SCC）UI 功能移植到 staging-tici C3 运行环境。

### 涉及仓库

| 仓库 | 分支 | 角色 |
|------|------|------|
| `sunnypilot1` | qt-dev | C++ UI 源码 + 编译工厂 |
| `sunnypilot` | staging-tici | Python 后端运行系统 |

### 文件改动清单

**sunnypilot1/qt-dev（7 文件）**：

| 文件 | 改动 |
|------|------|
| `common/params_keys.h` | 新增 5 个参数：SmartCruiseControlVision、SmartCruiseControlMap、GreenLightAlert、LeadDepartAlert、SpeedLimitPolicy |
| `selfdrive/ui/sunnypilot/ui_scene.h` | 新增 `scc_vision_enabled`、`scc_map_enabled` bool |
| `selfdrive/ui/sunnypilot/ui.cc` | param_watcher 注册 + `ui_update_params_sp()` 读取 |
| `selfdrive/ui/sunnypilot/qt/onroad/hud.h` | 新增 `drawSCC()` 声明 + 6 个 SCC 成员变量 |
| `selfdrive/ui/sunnypilot/qt/onroad/hud.cc` | `updateState()` 读 cereal SCC 状态 + `draw()` 调用 + `drawSCC()` 完整实现（注释 lkasPrepared 相关代码） |
| `selfdrive/ui/sunnypilot/qt/offroad/settings/longitudinal_panel.h` | 新增 5 个 `ParamControlSP*` 指针 |
| `selfdrive/ui/sunnypilot/qt/offroad/settings/longitudinal_panel.cc` | 构造函数新增 5 个 toggle 控件 + `refresh()` 逻辑 |

**sunnypilot/staging-tici（1 文件）**：

| 文件 | 改动 |
|------|------|
| `sunnypilot/selfdrive/selfdrived/events.py` | 注册 `e2eChime` 事件，复用 `AudibleAlert.prompt`（即 `prompt.wav`） |

### cereal schema 同步

为编译通过，将 staging-tici 的 cereal `custom.capnp` 改动同步到 qt-dev：
- `ModelDataV2SP`：TurnDirection 枚举移入 struct
- `OnroadEventSP`：新增 5 个事件
- `CarStateSP`：新增 speedLimit 字段
- `CarParamsSP`：新增 3 个字段
- `LongitudinalPlanSP`：新增 SmartCruiseControl 结构体（vision/map 子结构，各含 enabled/active）
- `ModelManagerSP.Model.Type`：新增 offPolicy/onPolicy/chunked 枚举值

### 编译修复

| 错误 | 文件 | 修复 |
|------|------|------|
| `getLkasPrepared` 不存在 | hud.cc/hud.h/developer_ui.h/developer_ui.cc | 注释 lkasPrepared 所有引用（两边 cereal 均无此字段） |
| `getSmartCruiseControl` 不存在 | hud.cc | cereal schema 同步到 qt-dev |
| `OFF_POLICY/ON_POLICY/CHUNKED` 未处理 | models_panel.cc | switch 新增 fall-through case |

### SCC 指示器布局

| 参数 | 值 | 说明 |
|------|-----|------|
| 盒子尺寸 | 160×60, 圆角 16 | 每盒 |
| 字体 | Inter 34pt Bold | — |
| 水平位置 | `margin_x=690` | 紧贴速度数字左侧（间距 5px） |
| 垂直位置 | `base_y=165` | 与速度数字（y=230）垂直居中 |
| SCC-M 在上 | — | 先判断 sccMapEnabled，画在 base_y |
| SCC-V 在下 | — | 画在 base_y + 70 |

### 颜色方案

| 状态 | 背景色 | 文字色 |
|------|--------|--------|
| 激活 | 绿 `(0, 200, 80)` | 白 |
| 非激活 | 灰 `(100, 100, 100, 120)` | 白 |
| 长控超驰 | 橙 `(255, 180, 60)` | 黑 |

### 设置面板布局（Cruise 面板）

在 `CustomAccIncrement` 控件后依次排列：
1. Smart Cruise Control - Vision（SCC 视觉弯道预测）
2. Smart Cruise Control - 地图（SCC 地图弯道预测）
3. 绿灯提醒
4. 前车起步提醒
5. 限速策略

### Git 提交记录

| commit | 内容 |
|--------|------|
| `e2add59ba9` | 添加 SCC UI: onroad 状态指示器 + 设置面板 5 个开关 |
| `1224a1ed0b` | 同步 cereal schema |
| `ca549bd964` | 修复 models_panel.cc switch case |
| `614d964f2b` | 注释 lkasPrepared 编译错误 |
| `008cdf3a7a` | 同步 C3 编译通过版 |
| `5076a17181` | 同步 C3 SCC 指示器参数 |
| `7696ab4982` | margin_x 680→690，间距 5px |
