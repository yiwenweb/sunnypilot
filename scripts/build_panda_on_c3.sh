#!/bin/bash
# =============================================================================
# BYD Panda 固件编译脚本 — 在 C3 上运行
#
# 用途: 从 sunnypilot master-tici 分支获取完整源码，
#       替换 byd.h 安全文件，编译 panda 固件，
#       然后将编译好的固件复制到你的 staging-tici 分支。
#
# 使用方法:
#   1. SSH 到 C3: ssh comma@<C3_IP>
#   2. 确保 /data/openpilot 是你的 staging-tici 分支
#   3. 运行: bash /data/openpilot/scripts/build_panda_on_c3.sh
# =============================================================================

set -e

echo "========================================="
echo "BYD Panda 固件编译脚本"
echo "========================================="

# 路径定义
OPENPILOT_DIR="/data/openpilot"
BUILD_DIR="/data/panda_build"
PANDA_OBJ_DIR="$OPENPILOT_DIR/panda/board/obj"

# Step 1: 确保当前 openpilot 目录存在
if [ ! -d "$OPENPILOT_DIR" ]; then
    echo "错误: $OPENPILOT_DIR 不存在"
    exit 1
fi

# Step 2: 确保 prebuilt 文件存在（防止 staging-tici 启动时报错）
touch "$OPENPILOT_DIR/prebuilt"
echo "[OK] prebuilt 标记已恢复"

# Step 3: 拉取最新代码（确保 byd.h 是最新的）
echo ""
echo ">>> Step 1: 拉取最新代码..."
cd "$OPENPILOT_DIR"
git pull origin staging-tici || echo "警告: git pull 失败，继续使用本地代码"

# Step 4: Clone master-tici 分支（有完整源码）到临时目录
echo ""
echo ">>> Step 2: 克隆 sunnypilot master-tici 分支（完整源码）..."
rm -rf "$BUILD_DIR"
# 浅克隆，只要最新的一个 commit，节省空间和时间
git clone --depth 1 --branch master-tici https://github.com/sunnypilot/sunnypilot.git "$BUILD_DIR"
echo "[OK] master-tici 克隆完成"

# Step 5: 复制你的 byd.h 和 safety.h 到编译目录
echo ""
echo ">>> Step 3: 复制 BYD safety 文件到编译目录..."

# byd.h — 你的自定义安全模式
cp "$OPENPILOT_DIR/opendbc_repo/opendbc/safety/modes/byd.h" \
   "$BUILD_DIR/opendbc_repo/opendbc/safety/modes/byd.h"
echo "[OK] byd.h 已复制"

# safety.h — 确保 SAFETY_BYD 已注册
cp "$OPENPILOT_DIR/opendbc_repo/opendbc/safety/safety.h" \
   "$BUILD_DIR/opendbc_repo/opendbc/safety/safety.h"
echo "[OK] safety.h 已复制"

# safety_declarations.h — 确保 SAFETY_BYD 常量已定义
cp "$OPENPILOT_DIR/opendbc_repo/opendbc/safety/safety_declarations.h" \
   "$BUILD_DIR/opendbc_repo/opendbc/safety/safety_declarations.h"
echo "[OK] safety_declarations.h 已复制"

# 复制 sunnypilot MADS 相关的 safety 文件（如果存在）
if [ -d "$OPENPILOT_DIR/opendbc_repo/opendbc/safety/sunnypilot" ]; then
    cp -r "$OPENPILOT_DIR/opendbc_repo/opendbc/safety/sunnypilot/"* \
       "$BUILD_DIR/opendbc_repo/opendbc/safety/sunnypilot/" 2>/dev/null || true
    echo "[OK] sunnypilot safety 文件已复制"
fi

# Step 6: 编译 panda 固件
echo ""
echo ">>> Step 4: 编译 panda 固件..."
cd "$BUILD_DIR"

# 使用 scons 编译 panda
# master-tici 分支应该有 SConstruct 文件
if [ -f "$BUILD_DIR/SConstruct" ]; then
    echo "找到 SConstruct，使用 scons 编译..."
    scons -j$(nproc) panda/
else
    echo "未找到 SConstruct，尝试直接在 panda 目录编译..."
    cd "$BUILD_DIR/panda"
    if [ -f "SConstruct" ]; then
        scons -j$(nproc)
    elif [ -f "board/SConscript" ]; then
        cd board
        make -j$(nproc) 2>/dev/null || scons -j$(nproc)
    else
        echo "错误: 找不到编译入口文件"
        echo "目录内容:"
        ls -la "$BUILD_DIR/panda/board/"
        exit 1
    fi
fi

echo "[OK] 编译完成"

# Step 7: 复制编译好的固件到你的 staging-tici 分支
echo ""
echo ">>> Step 5: 复制编译好的固件..."

# 备份旧固件
if [ -d "$PANDA_OBJ_DIR" ]; then
    cp -r "$PANDA_OBJ_DIR" "${PANDA_OBJ_DIR}.bak.$(date +%Y%m%d%H%M%S)"
    echo "[OK] 旧固件已备份"
fi

# 复制新固件
BUILD_OBJ_DIR="$BUILD_DIR/panda/board/obj"
if [ -f "$BUILD_OBJ_DIR/panda.bin.signed" ]; then
    cp "$BUILD_OBJ_DIR/panda.bin.signed" "$PANDA_OBJ_DIR/panda.bin.signed"
    echo "[OK] panda.bin.signed 已更新"
else
    echo "警告: panda.bin.signed 未找到"
    echo "编译输出目录内容:"
    ls -la "$BUILD_OBJ_DIR/" 2>/dev/null || echo "目录不存在"
fi

if [ -f "$BUILD_OBJ_DIR/panda_h7.bin.signed" ]; then
    cp "$BUILD_OBJ_DIR/panda_h7.bin.signed" "$PANDA_OBJ_DIR/panda_h7.bin.signed"
    echo "[OK] panda_h7.bin.signed 已更新"
fi

if [ -f "$BUILD_OBJ_DIR/bootstub.panda.bin" ]; then
    cp "$BUILD_OBJ_DIR/bootstub.panda.bin" "$PANDA_OBJ_DIR/bootstub.panda.bin"
    echo "[OK] bootstub.panda.bin 已更新"
fi

if [ -f "$BUILD_OBJ_DIR/bootstub.panda_h7.bin" ]; then
    cp "$BUILD_OBJ_DIR/bootstub.panda_h7.bin" "$PANDA_OBJ_DIR/bootstub.panda_h7.bin"
    echo "[OK] bootstub.panda_h7.bin 已更新"
fi

# Step 8: 清理临时编译目录（节省空间）
echo ""
echo ">>> Step 6: 清理临时文件..."
rm -rf "$BUILD_DIR"
echo "[OK] 临时编译目录已清理"

# Step 9: 提交更新的固件到 git
echo ""
echo ">>> Step 7: 提交固件更新..."
cd "$OPENPILOT_DIR"
git add panda/board/obj/
git commit -m "panda: rebuild firmware with SAFETY_BYD support" || echo "没有变化需要提交"

echo ""
echo "========================================="
echo "完成！"
echo "========================================="
echo ""
echo "下一步:"
echo "  1. 重启设备: sudo reboot"
echo "  2. pandad 会自动检测到新固件并烧录"
echo "  3. 如果要推送到 GitHub: git push origin staging-tici"
echo ""
