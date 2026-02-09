#!/bin/bash
# =============================================================================
# BYD Panda 固件编译脚本 v2 — 在 C3 上运行
#
# 核心改进:
#   1. 分步克隆子模块，确保 panda 和 opendbc_repo 完整
#   2. 复制完整的 safety 目录（byd.h + safety.h + safety_declarations.h）
#   3. 用 git add -f 强制提交固件（绕过 .gitignore 的 obj/ 规则）
#   4. 编译前验证所有关键文件存在
#
# 使用方法:
#   ssh comma@<C3_IP>
#   pkill -9 -f selfdrive; pkill -9 -f pandad; sleep 3
#   bash /data/openpilot/scripts/build_panda_on_c3.sh
# =============================================================================

set -e

echo "========================================="
echo "BYD Panda 固件编译脚本 v2"
echo "========================================="

OPENPILOT_DIR="/data/openpilot"
BUILD_DIR="/data/panda_build"
PANDA_OBJ_DIR="$OPENPILOT_DIR/panda/board/obj"

# --- Step 0: 前置检查 ---
if [ ! -d "$OPENPILOT_DIR" ]; then
    echo "错误: $OPENPILOT_DIR 不存在"
    exit 1
fi

# 确保 prebuilt 标记存在
touch "$OPENPILOT_DIR/prebuilt"

# --- Step 1: 拉取最新代码 ---
echo ""
echo ">>> Step 1: 拉取最新 staging-tici 代码..."
cd "$OPENPILOT_DIR"
git pull myrepo staging-tici || echo "警告: git pull 失败，继续使用本地代码"

# --- Step 2: 清理旧的编译目录 ---
echo ""
echo ">>> Step 2: 清理旧编译目录..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# --- Step 3: 克隆 master-tici（只需要 panda 子模块） ---
echo ""
echo ">>> Step 3: 克隆 sunnypilot master-tici..."
# 先浅克隆主仓库（不含子模块）
git clone --depth 1 --branch master-tici https://github.com/sunnypilot/sunnypilot.git "$BUILD_DIR"
echo "[OK] 主仓库克隆完成"

# 手动初始化并克隆需要的子模块
cd "$BUILD_DIR"
echo "初始化 panda 子模块..."
git submodule update --init --depth 1 panda
echo "[OK] panda 子模块完成"

echo "初始化 opendbc_repo 子模块..."
git submodule update --init --depth 1 opendbc_repo
echo "[OK] opendbc_repo 子模块完成"

# 验证关键目录存在
echo ""
echo ">>> 验证子模块..."
if [ ! -d "$BUILD_DIR/panda/board" ]; then
    echo "错误: panda/board 目录不存在！子模块克隆失败"
    echo "panda 目录内容:"
    ls -la "$BUILD_DIR/panda/" 2>/dev/null || echo "  (空)"
    exit 1
fi
echo "[OK] panda/board 存在"

if [ ! -d "$BUILD_DIR/opendbc_repo/opendbc/safety/modes" ]; then
    echo "错误: opendbc_repo/opendbc/safety/modes 不存在！"
    # 尝试创建
    mkdir -p "$BUILD_DIR/opendbc_repo/opendbc/safety/modes"
    echo "[WARN] 已手动创建 modes 目录"
fi
echo "[OK] safety/modes 目录存在"


# --- Step 4: 复制整个 safety 目录 ---
echo ""
echo ">>> Step 4: 复制整个 safety 目录到编译目录..."

# 关键: 我们的 staging-tici 分支的 safety 目录包含:
#   - byd.h (BYD 安全模式)
#   - safety.h (注册了 SAFETY_BYD)
#   - safety_declarations.h (定义了 CanMsg 的 check_relay/disable_static_blocking 字段)
#   - lateral.h (引用了 sunnypilot/safety_mads.h)
#   - sunnypilot/safety_mads.h (MADS 支持)
#   - board/ 子目录 (CAN 驱动等)
#
# master-tici 的 safety 目录可能缺少这些文件或字段定义不同。
# 最安全的做法是用我们的整个 safety 目录覆盖 master-tici 的。

SRC_SAFETY_DIR="$OPENPILOT_DIR/opendbc_repo/opendbc/safety"
DST_SAFETY_DIR="$BUILD_DIR/opendbc_repo/opendbc/safety"

if [ ! -d "$SRC_SAFETY_DIR" ]; then
    echo "错误: $SRC_SAFETY_DIR 不存在！"
    exit 1
fi

# 用 cp -a 保留目录结构，覆盖所有文件
cp -a "$SRC_SAFETY_DIR/"* "$DST_SAFETY_DIR/"
echo "[OK] 整个 safety 目录已复制（覆盖 master-tici 版本）"

# 列出复制的关键文件
echo "  已复制的关键文件:"
for f in safety.h safety_declarations.h lateral.h helpers.h longitudinal.h modes/byd.h sunnypilot/safety_mads.h; do
    if [ -f "$DST_SAFETY_DIR/$f" ]; then
        echo "    [OK] $f"
    else
        echo "    [MISS] $f"
    fi
done

# --- Step 4b: 验证关键内容 ---
echo ""
echo ">>> 验证关键文件内容..."
DST_BYD_H="$DST_SAFETY_DIR/modes/byd.h"
DST_DECL_H="$DST_SAFETY_DIR/safety_declarations.h"
DST_SAFETY_H="$DST_SAFETY_DIR/safety.h"

echo "验证 byd.h 中的 check_relay 设置..."
if grep -q "check_relay = false" "$DST_BYD_H"; then
    echo "[OK] byd.h 包含 check_relay = false"
else
    echo "[WARN] byd.h 中未找到 check_relay = false！"
fi

echo "验证 safety_declarations.h 中的 SAFETY_BYD..."
if grep -q "SAFETY_BYD" "$DST_DECL_H"; then
    echo "[OK] SAFETY_BYD 已定义"
else
    echo "[WARN] SAFETY_BYD 未在 safety_declarations.h 中定义！"
fi

echo "验证 CanMsg 结构体字段..."
if grep -q "check_relay" "$DST_DECL_H"; then
    echo "[OK] CanMsg 包含 check_relay 字段"
else
    echo "[错误] CanMsg 缺少 check_relay 字段！这会导致 byd.h 的 .check_relay=false 被忽略！"
    exit 1
fi

if grep -q "disable_static_blocking" "$DST_DECL_H"; then
    echo "[OK] CanMsg 包含 disable_static_blocking 字段"
else
    echo "[WARN] CanMsg 缺少 disable_static_blocking 字段"
fi

echo "验证 safety.h 中的 byd_hooks..."
if grep -q "byd_hooks" "$DST_SAFETY_H"; then
    echo "[OK] safety.h 包含 byd_hooks"
else
    echo "[错误] safety.h 缺少 byd_hooks！"
    exit 1
fi

# --- Step 5: 编译 panda 固件 ---
echo ""
echo ">>> Step 5: 编译 panda 固件..."
cd "$BUILD_DIR"

# 尝试多种编译方式
if [ -f "$BUILD_DIR/SConstruct" ]; then
    echo "使用顶层 scons 编译 panda/..."
    scons -j$(nproc) panda/
elif [ -f "$BUILD_DIR/panda/SConstruct" ]; then
    echo "使用 panda/SConstruct 编译..."
    cd "$BUILD_DIR/panda"
    scons -j$(nproc)
elif [ -f "$BUILD_DIR/panda/board/Makefile" ]; then
    echo "使用 panda/board/Makefile 编译..."
    cd "$BUILD_DIR/panda/board"
    make -j$(nproc)
else
    echo "错误: 找不到编译入口！"
    echo "BUILD_DIR 内容:"
    ls -la "$BUILD_DIR/"
    echo "panda 目录:"
    ls -la "$BUILD_DIR/panda/" 2>/dev/null
    echo "panda/board 目录:"
    ls -la "$BUILD_DIR/panda/board/" 2>/dev/null
    exit 1
fi

echo "[OK] 编译完成"

# --- Step 6: 验证编译输出 ---
echo ""
echo ">>> Step 6: 验证编译输出..."
BUILD_OBJ_DIR="$BUILD_DIR/panda/board/obj"

if [ ! -f "$BUILD_OBJ_DIR/panda.bin.signed" ]; then
    echo "错误: panda.bin.signed 未生成！"
    echo "obj 目录内容:"
    ls -la "$BUILD_OBJ_DIR/" 2>/dev/null || echo "  obj 目录不存在"
    exit 1
fi

echo "编译输出:"
ls -la "$BUILD_OBJ_DIR/"*.bin* 2>/dev/null

# --- Step 7: 复制固件到 staging-tici ---
echo ""
echo ">>> Step 7: 复制固件..."

# 确保目标目录存在
mkdir -p "$PANDA_OBJ_DIR"

# 备份旧固件
if [ -f "$PANDA_OBJ_DIR/panda.bin.signed" ]; then
    cp "$PANDA_OBJ_DIR/panda.bin.signed" "$PANDA_OBJ_DIR/panda.bin.signed.bak"
    echo "[OK] 旧 panda.bin.signed 已备份"
fi

# 复制新固件
for f in panda.bin.signed panda_h7.bin.signed bootstub.panda.bin bootstub.panda_h7.bin; do
    if [ -f "$BUILD_OBJ_DIR/$f" ]; then
        cp "$BUILD_OBJ_DIR/$f" "$PANDA_OBJ_DIR/$f"
        echo "[OK] $f 已更新 ($(stat -c%s "$PANDA_OBJ_DIR/$f") bytes)"
    fi
done

# --- Step 8: 清理 ---
echo ""
echo ">>> Step 8: 清理临时编译目录..."
rm -rf "$BUILD_DIR"
echo "[OK] 已清理"

# --- Step 9: 提交（用 -f 强制添加，绕过 .gitignore） ---
echo ""
echo ">>> Step 9: 提交固件..."
cd "$OPENPILOT_DIR"
git add -f panda/board/obj/panda.bin.signed panda/board/obj/panda_h7.bin.signed \
         panda/board/obj/bootstub.panda.bin panda/board/obj/bootstub.panda_h7.bin 2>/dev/null || true
git commit -m "panda: rebuild firmware with SAFETY_BYD (check_relay=false)" || echo "没有变化需要提交"

echo ""
echo "========================================="
echo "编译完成！"
echo "========================================="
echo ""
echo "下一步:"
echo "  1. 烧录固件: python3 -c \"from panda import Panda; p=Panda(); p.flash(); p.close()\""
echo "  2. 等待3秒后验证: python3 -c \"from panda import Panda; p=Panda(); print(p.get_version()); p.close()\""
echo "  3. 重启: sudo reboot -f"
echo ""
