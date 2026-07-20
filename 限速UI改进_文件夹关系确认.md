# 限速 UI 改进 - 文件夹关系确认

> 创建时间：2026-07-15  
> 目的：明确编译工作流，避免改错地方

---

## 一、桌面目录结构

```
c:\Users\yiwen\Desktop\1\
├── sunnypilot/           ← 运行系统源码（staging-tici 分支）
│   └── 绑定到 C3 /data/openpilot/
│
├── sunnypilot1/          ← ✅ 编译工厂源码（qt-dev 分支）★ 我们要改这里
│   └── 绑定到 C3 /data/panda_build/
│
├── sunnypilot_master_tici/  ← 备份目录（未使用）
├── sunnypilot-android/      ← Android App 源码
└── 其他文件...
```

---

## 二、Git 配置确认

### sunnypilot1/ 目录（编译工厂）

**当前状态**：
```bash
路径：c:\Users\yiwen\Desktop\1\sunnypilot1
分支：qt-dev ✅
远端：
  - origin → https://github.com/sunnypilot/sunnypilot.git (官方上游，只读)
  - yiwen  → https://github.com/yiwenweb/sunnypilot.git (个人仓库，可推送)
```

**核心事实**：
- ✅ 这是唯一有完整 Qt C++ 源码的目录
- ✅ 这是我们编辑代码的地方
- ✅ 改动后推送到 `yiwen` remote 的 `qt-dev` 分支
- ✅ C3 上从 `/data/panda_build/` 拉取并编译

---

## 三、要修改的文件清单

### 方案 B 实施需要改动的文件：

#### 1. 核心 UI 代码（必改）

| 文件路径 | 作用 | 改动量 |
|---------|------|--------|
| `selfdrive/ui/sunnypilot/qt/onroad/hud.h` | HUD 头文件 | +10 行（新方法声明 + 缓存成员） |
| `selfdrive/ui/sunnypilot/qt/onroad/hud.cc` | HUD 实现 | +150 行（方案 B 完整代码） |

**具体位置**：
```
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\qt\onroad\hud.h
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\qt\onroad\hud.cc
```

#### 2. 参数注册（必改）

| 文件路径 | 作用 | 改动量 |
|---------|------|--------|
| `common/params_keys.h` | 参数键注册 | +5 行（新参数键） |

**具体位置**：
```
c:\Users\yiwen\Desktop\1\sunnypilot1\common\params_keys.h
```

**新增参数键**：
```cpp
{"SpeedLimitStyle", {PERSISTENT | BACKUP, INT, "1"}},               // 0=矩形 1=圆形 2=大圆
{"SpeedLimitWarnThreshold", {PERSISTENT | BACKUP, INT, "10"}},     // 超速警告阈值（km/h）
{"SpeedLimitDangerThreshold", {PERSISTENT | BACKUP, INT, "20"}},   // 严重超速阈值（km/h）
{"SpeedLimitShowSource", {PERSISTENT | BACKUP, BOOL, "0"}},        // 显示数据源图标
{"SpeedLimitColorMAX", {PERSISTENT | BACKUP, BOOL, "1"}},          // MAX 标签变色
```

#### 3. 场景状态字段（必改）

| 文件路径 | 作用 | 改动量 |
|---------|------|--------|
| `selfdrive/ui/sunnypilot/ui_scene.h` | 场景结构体 | +5 行（新字段） |
| `selfdrive/ui/sunnypilot/ui.cc` | 参数读取 | +6 行（读取逻辑） |

**具体位置**：
```
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\ui_scene.h
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\ui.cc
```

#### 4. 设置面板（可选，阶段 3 实施）

| 文件路径 | 作用 | 改动量 |
|---------|------|--------|
| `selfdrive/ui/sunnypilot/qt/offroad/settings/sunny_features_panel.cc` | SP Features 面板 | +30 行（3 个 toggle） |

**具体位置**：
```
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\qt\offroad\settings\sunny_features_panel.cc
```

---

## 四、工作流程（关键步骤）

### 阶段 1：本地编辑（在 sunnypilot1/）

```bash
# 1. 打开文件编辑
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\qt\onroad\hud.cc
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\qt\onroad\hud.h
c:\Users\yiwen\Desktop\1\sunnypilot1\common\params_keys.h
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\ui_scene.h
c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\ui.cc

# 2. 提交到本地 Git
cd c:\Users\yiwen\Desktop\1\sunnypilot1
git add selfdrive/ui/sunnypilot/qt/onroad/hud.cc
git add selfdrive/ui/sunnypilot/qt/onroad/hud.h
git add common/params_keys.h
git add selfdrive/ui/sunnypilot/ui_scene.h
git add selfdrive/ui/sunnypilot/ui.cc
git commit -m "feat(ui): 实现方案B限速圆标（并排布局）"

# 3. 推送到 GitHub
git push yiwen qt-dev
```

### 阶段 2：C3 编译（在 /data/panda_build/）

```bash
# SSH 连接 C3
ssh comma@<C3_IP>

# 进入编译目录
cd /data/panda_build

# 拉取最新代码
git fetch yiwen qt-dev
git checkout yiwen/qt-dev -- selfdrive/ui/sunnypilot/qt/onroad/hud.cc
git checkout yiwen/qt-dev -- selfdrive/ui/sunnypilot/qt/onroad/hud.h
git checkout yiwen/qt-dev -- common/params_keys.h
git checkout yiwen/qt-dev -- selfdrive/ui/sunnypilot/ui_scene.h
git checkout yiwen/qt-dev -- selfdrive/ui/sunnypilot/ui.cc

# 编译 UI 二进制
source /usr/local/venv/bin/activate
export PYTHONPATH=/data/panda_build
scons -j4 selfdrive/ui/ui

# 【关键】重编 params_pyx.so（避免参数持久化陷阱）
scons -j4 common/params_pyx.so
```

### 阶段 3：部署到运行系统（/data/openpilot/）

```bash
# 停止 UI 进程
sudo pkill -f manager
sudo pkill -f "selfdrive/ui/ui"
sleep 3

# 备份 + 替换 UI 二进制
cp /data/openpilot/selfdrive/ui/ui /data/openpilot/selfdrive/ui/ui.bak
cp /data/panda_build/selfdrive/ui/ui /data/openpilot/selfdrive/ui/ui

# 【关键】替换 params_pyx.so
cp /data/panda_build/common/params_pyx.so /data/openpilot/common/params_pyx.so

# 重启
reboot
```

---

## 五、危险操作检查清单

### ❌ 绝对不要改这些地方：

1. **c:\Users\yiwen\Desktop\1\sunnypilot/**
   - 这是 staging-tici 分支，没有 Qt C++ 源码
   - 这是运行系统源码，改了也不会被编译

2. **C3 上的 /data/openpilot/**
   - 这是运行系统，没有 UI 源码
   - 直接改 UI 文件会被 Git 覆盖

3. **直接改 /data/openpilot/selfdrive/ui/ui 二进制**
   - 这是编译产物，不能直接编辑
   - 必须从 /data/panda_build/ 编译后复制

### ✅ 正确的流程：

```
桌面 sunnypilot1/ (qt-dev)
  ↓ 编辑 .cc/.h
  ↓ git commit
  ↓ git push yiwen qt-dev
  ↓
C3 /data/panda_build/ (master-tici)
  ↓ git checkout yiwen/qt-dev -- <文件>
  ↓ scons 编译
  ↓ 产生 selfdrive/ui/ui 二进制
  ↓
C3 /data/openpilot/ (staging-tici)
  ↓ cp ui 二进制
  ↓ cp params_pyx.so
  ↓ reboot
  ↓
  ✅ 新 UI 生效
```

---

## 六、快速验证命令

### 验证当前在正确的目录：

```powershell
# Windows 桌面
cd c:\Users\yiwen\Desktop\1\sunnypilot1
git branch  # 应该显示 * qt-dev
dir selfdrive\ui\sunnypilot\qt\onroad\hud.cc  # 应该存在
```

### 验证 C3 目录状态：

```bash
# SSH 到 C3
cd /data/panda_build
git branch  # 应该显示 * master-tici
git remote -v | grep yiwen  # 应该有 yiwen remote
ls selfdrive/ui/sunnypilot/qt/onroad/hud.cc  # 应该存在
```

---

## 七、文件路径速查表

| 功能 | 桌面路径（改这里） | C3 编译路径 | C3 运行路径（只读） |
|------|-------------------|------------|-------------------|
| HUD 实现 | `c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\qt\onroad\hud.cc` | `/data/panda_build/selfdrive/ui/sunnypilot/qt/onroad/hud.cc` | `/data/openpilot/selfdrive/ui/sunnypilot/qt/onroad/hud.cc` ❌ 不存在 |
| HUD 头文件 | `c:\Users\yiwen\Desktop\1\sunnypilot1\selfdrive\ui\sunnypilot\qt\onroad\hud.h` | `/data/panda_build/selfdrive/ui/sunnypilot/qt/onroad/hud.h` | 同上 ❌ |
| 参数键 | `c:\Users\yiwen\Desktop\1\sunnypilot1\common\params_keys.h` | `/data/panda_build/common/params_keys.h` | `/data/openpilot/common/params_keys.h` ⚠️ 存在但不编译 |
| UI 二进制 | ❌ 不存在 | `/data/panda_build/selfdrive/ui/ui` ✅ 编译产物 | `/data/openpilot/selfdrive/ui/ui` ✅ 运行文件 |
| params.so | ❌ 不存在 | `/data/panda_build/common/params_pyx.so` ✅ 编译产物 | `/data/openpilot/common/params_pyx.so` ✅ 运行文件 |

---

## 八、常见错误与修正

### 错误 1：改了 sunnypilot/ 目录

**症状**：改了代码，C3 编译时找不到改动

**原因**：改错目录了，应该改 `sunnypilot1/`（qt-dev 分支）

**修正**：
```bash
cd c:\Users\yiwen\Desktop\1\sunnypilot1
# 重新编辑文件
```

### 错误 2：参数重启后失效

**症状**：设置面板的开关重启后变回关闭

**原因**：未重编 `params_pyx.so`，`manager.py` 的 `clearAll()` 删除了新参数

**修正**（档案已记录）：
```bash
cd /data/panda_build
scons -j4 common/params_pyx.so
cp /data/panda_build/common/params_pyx.so /data/openpilot/common/params_pyx.so
reboot
```

### 错误 3：cp ui 时报 "Text file busy"

**症状**：`cp` 命令失败，提示文件正在使用

**原因**：UI 进程正在运行，二进制被内核锁定

**修正**：
```bash
sudo pkill -f manager
sudo pkill -f "selfdrive/ui/ui"
sleep 3  # 等待进程完全退出
cp /data/panda_build/selfdrive/ui/ui /data/openpilot/selfdrive/ui/ui
```

---

## 九、总结

### ✅ 核心原则：

1. **只改 sunnypilot1/ 目录**（qt-dev 分支）
2. **推送到 yiwen remote**
3. **C3 上在 /data/panda_build/ 编译**
4. **复制到 /data/openpilot/ 运行**
5. **必须重编 params_pyx.so**（新增参数时）

### 📋 下一步：

- [ ] 确认已理解文件夹关系
- [ ] 开始编写代码
- [ ] 本地 commit + push
- [ ] C3 编译测试

