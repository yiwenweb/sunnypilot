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
官方上游:  https://github.com/sunnypilot/sunnypilot.git   (remote: origin)
个人仓库:  https://github.com/yiwenweb/sunnypilot.git      (remote: yiwen)
```

### 桌面 sunnypilot1 配置

```powershell
origin → https://github.com/sunnypilot/sunnypilot.git     # 官方，只读
yiwen  → https://github.com/yiwenweb/sunnypilot.git       # 个人，推送

分支: qt-dev  (基于 master-tici 创建)
```

```powershell
cd C:\Users\yiwen\Desktop\1\sunnypilot1
git remote add yiwen https://github.com/yiwenweb/sunnypilot.git
git checkout -b qt-dev
git push yiwen qt-dev
```

### C3 /data/panda_build 配置

```bash
cd /data/panda_build
git remote add yiwen https://github.com/yiwenweb/sunnypilot.git
git fetch yiwen qt-dev
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
| 6 | **RoadName 道路名称** | `liveMapDataSP.roadName` | ⭐⭐⭐ 中-高 |
| 7 | **SpeedLimit 限速标志** | `longitudinalPlanSP.speedLimit` | ⭐⭐⭐ 高 |
| 8 | **SmartCruiseControl SCC状态** | `longitudinalPlanSP.smartCruiseControl` | ⭐⭐⭐ 高 |
| 9 | **SteeringArc 转向弧** | 扭矩/角度数据 | ⭐⭐ 中 |

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

## 八、移植记录

| 日期 | 功能 | 文件改动 | 状态 |
|------|------|---------|------|
| 2026-07-04 | **AccelBar 底部加减速横条** | `hud.h/cc` `ui_scene.h` `ui.cc` `params_keys.h` `visuals_panel.cc` | ✅ 代码完成 |
| 2026-07-04 | **SP Features 设置面板** | `sunny_features_panel.h/cc`(新建) `settings.cc` `SConscript` `icon_sunny_features.svg`(新建) | ✅ 代码完成 |
| 2026-07-04 | **修复 onroad 崩溃** | `ui.cc` 订阅列表 +`liveMapDataSP` | ✅ 已修复 |
| 2026-07-07 | **屏幕实时流（ScreenStreaming）** | `screenstreamer.h/cc` `window.h/cc` `sunny_features_panel.cc` | ✅ 已完成 |
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

---

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

---

## 十、相关文档

- BYD 唐 DM 2018 适配技术笔记：`BYD_唐DM_2018_sunnypilot适配技术笔记.md`
- sunnypilot 官方文档：https://docs.sunnypilot.com
- openpilot 开发者文档：https://docs.comma.ai
- 本档案所在仓库：https://github.com/yiwenweb/sunnypilot (分支: staging-tici)
