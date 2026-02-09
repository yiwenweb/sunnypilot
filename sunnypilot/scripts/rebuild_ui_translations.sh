#!/bin/bash
# ============================================================
# 在 C3 上重编译 UI 以更新内嵌翻译
#
# 背景: staging-tici 是预编译分支，翻译 .qm 文件被嵌入到
#       UI 二进制(selfdrive/ui/ui)中。更新 .qm 文件后需要
#       重编译 UI 才能生效。
#
# 用法: SSH 到 C3，然后运行:
#   cd /data/openpilot && bash scripts/rebuild_ui_translations.sh
# ============================================================
set -e
BASEDIR="/data/openpilot"
cd "$BASEDIR"

echo "========================================="
echo "  重编译 UI 以更新翻译"
echo "========================================="

# ---- 1. 拉取最新代码 ----
echo ""
echo "[1/6] 拉取最新代码..."
git pull origin staging-tici || echo "⚠ git pull 失败，使用本地文件"

echo "  .ts 未翻译: $(grep -c 'type=\"unfinished\"' selfdrive/ui/translations/main_zh-CHS.ts 2>/dev/null || echo 0)"
echo "  .qm 大小: $(stat -c%s selfdrive/ui/translations/main_zh-CHS.qm 2>/dev/null) bytes"

# ---- 2. 备份原始 UI ----
echo ""
echo "[2/6] 备份原始 UI..."
cp selfdrive/ui/ui selfdrive/ui/ui.original
echo "  已备份 ($(stat -c%s selfdrive/ui/ui.original) bytes)"

# ---- 3. 从 upstream 获取构建文件 ----
echo ""
echo "[3/6] 获取构建配置..."
git remote add upstream https://github.com/sunnypilot/sunnypilot.git 2>/dev/null || true
git fetch upstream master-tici --depth=1 2>&1 | tail -3

# 获取构建所需文件
for f in SConstruct; do
    git show upstream/master-tici:$f > $f 2>/dev/null
    echo "  ✓ $f"
done

# 获取 site_scons 目录
git checkout upstream/master-tici -- site_scons/ 2>/dev/null
echo "  ✓ site_scons/"

# ---- 4. 临时移除 prebuilt ----
echo ""
echo "[4/6] 准备编译环境..."
PREBUILT_EXISTED=0
if [ -f prebuilt ]; then
    mv prebuilt prebuilt.disabled
    PREBUILT_EXISTED=1
    echo "  prebuilt 已临时禁用"
fi
export PYTHONPATH="$BASEDIR"

# ---- 5. 编译 UI ----
echo ""
echo "[5/6] 编译 selfdrive/ui/ui （约 15-30 分钟）..."
echo "  请耐心等待..."
echo ""

BUILD_OK=0
if scons -j4 selfdrive/ui/ui 2>&1 | tee /tmp/ui_build.log | tail -50; then
    BUILD_OK=1
fi

# ---- 6. 清理 ----
echo ""
echo "[6/6] 清理..."

# 恢复 prebuilt
if [ $PREBUILT_EXISTED -eq 1 ]; then
    mv prebuilt.disabled prebuilt
fi

# 删除构建文件（不污染 staging-tici）
rm -f SConstruct
rm -rf site_scons/
rm -f selfdrive/assets/assets.cc 2>/dev/null
rm -rf .sconsign.dblite 2>/dev/null

if [ $BUILD_OK -eq 1 ] && [ -f selfdrive/ui/ui ] && [ selfdrive/ui/ui -nt selfdrive/ui/ui.original ]; then
    NEW_SIZE=$(stat -c%s selfdrive/ui/ui)
    echo ""
    echo "========================================="
    echo "  ✅ 编译成功！"
    echo "  新 UI 大小: $NEW_SIZE bytes"
    echo "  原始备份: selfdrive/ui/ui.original"
    echo ""
    echo "  重启以加载新翻译:"
    echo "    sudo reboot"
    echo ""
    echo "  如需恢复原始 UI:"
    echo "    cp selfdrive/ui/ui.original selfdrive/ui/ui"
    echo "    sudo reboot"
    echo "========================================="
else
    echo ""
    echo "========================================="
    echo "  ❌ 编译失败"
    echo "  恢复原始 UI..."
    cp selfdrive/ui/ui.original selfdrive/ui/ui
    echo "  完整日志: /tmp/ui_build.log"
    echo ""
    echo "  如果反复失败，可以尝试方案 A:"
    echo "    从 master-tici 分支获取 SConstruct"
    echo "    删除 prebuilt 文件"
    echo "    重启设备（系统会自动编译）"
    echo "========================================="
fi
