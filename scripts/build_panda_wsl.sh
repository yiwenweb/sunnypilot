#!/bin/bash
# =============================================================================
# BYD Panda 固件编译脚本 — 在 WSL Ubuntu 上运行
#
# 使用方法:
#   1. 打开 WSL Ubuntu 终端
#   2. cd /mnt/g/sunnypilot/sunnypilot
#   3. bash scripts/build_panda_wsl.sh
# =============================================================================

set -e

echo "========================================="
echo "BYD Panda 固件编译 (WSL Ubuntu)"
echo "========================================="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUILD_DIR="/tmp/panda_build"

echo "Repo 路径: $REPO_DIR"

# Step 1: 安装编译工具链
echo ""
echo ">>> Step 1: 检查/安装编译工具链..."

NEED_INSTALL=""
command -v arm-none-eabi-gcc &>/dev/null || NEED_INSTALL="gcc-arm-none-eabi"
command -v git &>/dev/null || NEED_INSTALL="$NEED_INSTALL git"
command -v make &>/dev/null || NEED_INSTALL="$NEED_INSTALL build-essential"
python3 -c "import SCons" 2>/dev/null || NEED_INSTALL="$NEED_INSTALL python3-pip"

if [ -n "$NEED_INSTALL" ]; then
    echo "安装: $NEED_INSTALL"
    sudo apt-get update
    sudo apt-get install -y $NEED_INSTALL
fi

if ! python3 -c "import SCons" 2>/dev/null; then
    echo "安装 scons..."
    pip3 install scons
fi

echo "[OK] 工具链就绪"
echo "  arm-none-eabi-gcc: $(arm-none-eabi-gcc --version 2>/dev/null | head -1)"

# Step 2: 克隆 master-tici + 初始化 panda 和 opendbc 子模块
echo ""
echo ">>> Step 2: 克隆 sunnypilot master-tici..."
rm -rf "$BUILD_DIR"
git clone --depth 1 --branch master-tici https://github.com/sunnypilot/sunnypilot.git "$BUILD_DIR"

echo "初始化 panda 和 opendbc 子模块..."
cd "$BUILD_DIR"
git submodule update --init --depth 1 panda
git submodule update --init --depth 1 opendbc_repo
echo "[OK] 子模块初始化完成"

# 验证目录结构
echo ""
echo "验证目录结构..."
ls "$BUILD_DIR/panda/board/" >/dev/null 2>&1 && echo "[OK] panda/board/ 存在" || { echo "错误: panda/board/ 不存在"; exit 1; }
ls "$BUILD_DIR/opendbc_repo/opendbc/safety/modes/" >/dev/null 2>&1 && echo "[OK] opendbc safety/modes/ 存在" || { echo "错误: opendbc safety/modes/ 不存在"; exit 1; }

# Step 3: 复制 BYD safety 文件
echo ""
echo ">>> Step 3: 复制 BYD safety 文件..."

cp "$REPO_DIR/opendbc_repo/opendbc/safety/modes/byd.h" \
   "$BUILD_DIR/opendbc_repo/opendbc/safety/modes/byd.h"
echo "[OK] byd.h"

cp "$REPO_DIR/opendbc_repo/opendbc/safety/safety.h" \
   "$BUILD_DIR/opendbc_repo/opendbc/safety/safety.h"
echo "[OK] safety.h"

cp "$REPO_DIR/opendbc_repo/opendbc/safety/safety_declarations.h" \
   "$BUILD_DIR/opendbc_repo/opendbc/safety/safety_declarations.h"
echo "[OK] safety_declarations.h"

# sunnypilot MADS safety 文件
if [ -d "$REPO_DIR/opendbc_repo/opendbc/safety/sunnypilot" ] && \
   [ -d "$BUILD_DIR/opendbc_repo/opendbc/safety/sunnypilot" ]; then
    cp -r "$REPO_DIR/opendbc_repo/opendbc/safety/sunnypilot/"* \
       "$BUILD_DIR/opendbc_repo/opendbc/safety/sunnypilot/"
    echo "[OK] sunnypilot MADS safety 文件"
fi

# Step 4: 编译
echo ""
echo ">>> Step 4: 编译 panda 固件..."
cd "$BUILD_DIR"
scons -j$(nproc) panda/

echo ""
echo "[OK] 编译完成！"

# Step 5: 复制固件回 repo
echo ""
echo ">>> Step 5: 复制固件..."

BUILD_OBJ="$BUILD_DIR/panda/board/obj"
REPO_OBJ="$REPO_DIR/panda/board/obj"

echo "编译输出文件:"
ls -la "$BUILD_OBJ/"*.bin* 2>/dev/null || echo "  (无 .bin 文件)"

for f in panda.bin.signed panda_h7.bin.signed bootstub.panda.bin bootstub.panda_h7.bin; do
    if [ -f "$BUILD_OBJ/$f" ]; then
        cp "$BUILD_OBJ/$f" "$REPO_OBJ/$f"
        echo "[OK] $f → $REPO_OBJ/$f"
    fi
done

# Step 6: 清理
echo ""
echo ">>> Step 6: 清理..."
rm -rf "$BUILD_DIR"

echo ""
echo "========================================="
echo "完成！固件已更新到: $REPO_OBJ/"
echo "========================================="
echo ""
echo "下一步:"
echo "  1. 在 Windows 的 repo 中: git add -A && git commit && git push"
echo "  2. C3 上: cd /data/openpilot && git pull"
echo "  3. 重启 C3: sudo reboot"
echo ""
