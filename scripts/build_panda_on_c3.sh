#!/bin/bash
# =============================================================================
# BYD Panda 固件编译脚本 v3 — 在 C3 上运行
#
# v3 改进: 缓存编译目录，避免每次重新克隆和下载
#   - 首次运行: 克隆 master-tici + 子模块（约2-5分钟）
#   - 后续运行: 跳过克隆，只更新 safety 文件并编译（约30秒）
#
# 使用方法:
#   ssh comma@<C3_IP>
#   pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
#   bash /data/openpilot/scripts/build_panda_on_c3.sh
#
# 强制重新克隆（如果缓存损坏）:
#   FORCE_CLEAN=1 bash /data/openpilot/scripts/build_panda_on_c3.sh
# =============================================================================

set -e

echo "========================================="
echo "BYD Panda 固件编译脚本 v3 (缓存版)"
echo "========================================="

OPENPILOT_DIR="/data/openpilot"
BUILD_DIR="/data/panda_build"
PANDA_OBJ_DIR="$OPENPILOT_DIR/panda/board/obj"

# --- Step 0: 前置检查 ---
if [ ! -d "$OPENPILOT_DIR" ]; then
    echo "错误: $OPENPILOT_DIR 不存在"
    exit 1
fi
touch "$OPENPILOT_DIR/prebuilt"

# --- Step 1: 拉取最新代码 ---
echo ""
echo ">>> Step 1: 拉取最新 staging-tici 代码..."
cd "$OPENPILOT_DIR"
git fetch myrepo staging-tici && git reset --hard myrepo/staging-tici || echo "警告: git 操作失败，继续使用本地代码"

# --- Step 2: 检查缓存的编译目录 ---
echo ""
NEED_CLONE=0

if [ "${FORCE_CLEAN:-0}" = "1" ]; then
    echo ">>> FORCE_CLEAN=1, 强制重新克隆..."
    rm -rf "$BUILD_DIR"
    NEED_CLONE=1
elif [ ! -d "$BUILD_DIR/panda/board" ]; then
    echo ">>> 编译目录不存在或不完整，需要克隆..."
    rm -rf "$BUILD_DIR"
    NEED_CLONE=1
elif [ ! -f "$BUILD_DIR/panda/SConstruct" ] && [ ! -f "$BUILD_DIR/panda/board/Makefile" ]; then
    echo ">>> 编译目录缺少构建文件，需要重新克隆..."
    rm -rf "$BUILD_DIR"
    NEED_CLONE=1
else
    echo ">>> [缓存命中] 编译目录已存在，跳过克隆 ✓"
fi

# --- Step 3: 克隆（仅首次或强制时） ---
if [ "$NEED_CLONE" = "1" ]; then
    echo ""
    echo ">>> Step 3: 克隆 sunnypilot master-tici (首次，后续会跳过)..."
    mkdir -p "$BUILD_DIR"
    git clone --depth 1 --branch master-tici https://github.com/sunnypilot/sunnypilot.git "$BUILD_DIR"
    echo "[OK] 主仓库克隆完成"

    cd "$BUILD_DIR"
    echo "初始化 panda 子模块..."
    git submodule update --init --depth 1 panda
    echo "[OK] panda 子模块完成"

    echo "初始化 opendbc_repo 子模块..."
    git submodule update --init --depth 1 opendbc_repo
    echo "[OK] opendbc_repo 子模块完成"
else
    echo ">>> Step 3: 跳过克隆 (使用缓存) ✓"
fi

# 验证关键目录
echo ""
echo ">>> 验证子模块..."
if [ ! -d "$BUILD_DIR/panda/board" ]; then
    echo "错误: panda/board 目录不存在！"
    exit 1
fi
echo "[OK] panda/board 存在"

if [ ! -d "$BUILD_DIR/opendbc_repo/opendbc/safety/modes" ]; then
    mkdir -p "$BUILD_DIR/opendbc_repo/opendbc/safety/modes"
    echo "[WARN] 已手动创建 modes 目录"
fi
echo "[OK] safety/modes 目录存在"

# --- Step 4: 复制 safety 目录（每次都执行，确保最新） ---
echo ""
echo ">>> Step 4: 复制 safety 目录到编译目录..."

SRC_SAFETY_DIR="$OPENPILOT_DIR/opendbc_repo/opendbc/safety"
DST_SAFETY_DIR="$BUILD_DIR/opendbc_repo/opendbc/safety"

if [ ! -d "$SRC_SAFETY_DIR" ]; then
    echo "错误: $SRC_SAFETY_DIR 不存在！"
    exit 1
fi

cp -a "$SRC_SAFETY_DIR/"* "$DST_SAFETY_DIR/"
echo "[OK] safety 目录已更新"

# 验证关键文件
for f in safety.h safety_declarations.h modes/byd.h; do
    if [ -f "$DST_SAFETY_DIR/$f" ]; then
        echo "  [OK] $f"
    else
        echo "  [MISS] $f"
        exit 1
    fi
done

# 快速验证关键内容
if grep -q "byd_hooks" "$DST_SAFETY_DIR/safety.h"; then
    echo "[OK] safety.h 包含 byd_hooks"
else
    echo "[错误] safety.h 缺少 byd_hooks！"
    exit 1
fi

# --- Step 5: 编译 panda 固件 ---
echo ""
echo ">>> Step 5: 编译 panda 固件..."
cd "$BUILD_DIR/panda"

if [ -f "SConstruct" ]; then
    scons -j$(nproc)
elif [ -f "board/Makefile" ]; then
    cd board
    make -j$(nproc)
else
    echo "错误: 找不到 SConstruct 或 Makefile！"
    exit 1
fi
echo "[OK] 编译完成"

# --- Step 6: 验证编译输出 ---
echo ""
echo ">>> Step 6: 验证编译输出..."
BUILD_OBJ_DIR="$BUILD_DIR/panda/board/obj"

if [ ! -f "$BUILD_OBJ_DIR/panda.bin.signed" ]; then
    echo "错误: panda.bin.signed 未生成！"
    ls -la "$BUILD_OBJ_DIR/" 2>/dev/null || echo "  obj 目录不存在"
    exit 1
fi
ls -la "$BUILD_OBJ_DIR/"*.bin* 2>/dev/null

# --- Step 7: 复制固件 + 提交 ---
echo ""
echo ">>> Step 7: 复制固件并提交..."
mkdir -p "$PANDA_OBJ_DIR"

for f in panda.bin.signed panda_h7.bin.signed bootstub.panda.bin bootstub.panda_h7.bin; do
    if [ -f "$BUILD_OBJ_DIR/$f" ]; then
        cp "$BUILD_OBJ_DIR/$f" "$PANDA_OBJ_DIR/$f"
        echo "[OK] $f ($(stat -c%s "$PANDA_OBJ_DIR/$f") bytes)"
    fi
done

cd "$OPENPILOT_DIR"
git add -f panda/board/obj/panda.bin.signed panda/board/obj/panda_h7.bin.signed \
         panda/board/obj/bootstub.panda.bin panda/board/obj/bootstub.panda_h7.bin 2>/dev/null || true
git commit -m "panda: rebuild firmware with latest byd.h" || echo "没有变化需要提交"

# 注意: 不再删除 BUILD_DIR，下次编译直接复用！

echo ""
echo "========================================="
echo "编译完成！"
echo "========================================="
echo ""
echo "下一步:"
echo "  1. 烧录: python3 -c \"from panda import Panda; p=Panda(); p.flash(); p.close()\""
echo "  2. 重启: sudo reboot -f"
echo ""
echo "提示: 编译缓存保留在 $BUILD_DIR"
echo "      下次运行将跳过克隆，直接编译（约30秒）"
echo "      如需强制重新克隆: FORCE_CLEAN=1 bash $0"
