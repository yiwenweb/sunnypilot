#!/bin/bash
# ============================================================
# 在 C3 上重编译翻译资源并注入 UI
#
# 原理: 用 rcc 把新的 .qm 编译成 C++ 源码，再编译成共享库，
#       通过 LD_PRELOAD 在 UI 启动时加载，覆盖内嵌的旧翻译。
#
# 用法: SSH 到 C3:
#   cd /data/openpilot
#   bash sunnypilot/scripts/rebuild_ui_translations.sh
# ============================================================
set -e
BASEDIR="/data/openpilot"
cd "$BASEDIR"

echo "=== 重编译翻译资源 ==="

# 1. 拉取最新代码
REMOTE=$(git remote | head -1)
echo "[1/5] 拉取最新代码 (remote: $REMOTE)..."
git pull "$REMOTE" staging-tici 2>/dev/null || echo "⚠ pull 失败，继续"
echo "  .qm 大小: $(stat -c%s selfdrive/ui/translations/main_zh-CHS.qm) bytes"
echo "  未翻译: $(grep -c 'type=\"unfinished\"' selfdrive/ui/translations/main_zh-CHS.ts 2>/dev/null || echo 0)"

# 2. 用 rcc 编译资源为 C++ 源码
echo ""
echo "[2/5] 生成资源 C++ 源码..."

TR_DIR="$BASEDIR/selfdrive/ui/translations"

# 生成 qrc 文件（使用绝对路径）
cat > /tmp/translations_assets.qrc << EOF
<!DOCTYPE RCC><RCC version="1.0">
<qresource>
<file alias="main_en">${TR_DIR}/main_en.qm</file>
<file alias="main_de">${TR_DIR}/main_de.qm</file>
<file alias="main_fr">${TR_DIR}/main_fr.qm</file>
<file alias="main_pt-BR">${TR_DIR}/main_pt-BR.qm</file>
<file alias="main_es">${TR_DIR}/main_es.qm</file>
<file alias="main_tr">${TR_DIR}/main_tr.qm</file>
<file alias="main_ar">${TR_DIR}/main_ar.qm</file>
<file alias="main_th">${TR_DIR}/main_th.qm</file>
<file alias="main_zh-CHT">${TR_DIR}/main_zh-CHT.qm</file>
<file alias="main_zh-CHS">${TR_DIR}/main_zh-CHS.qm</file>
<file alias="main_ko">${TR_DIR}/main_ko.qm</file>
<file alias="main_ja">${TR_DIR}/main_ja.qm</file>
</qresource>
</RCC>
EOF

rcc /tmp/translations_assets.qrc -o /tmp/translations_res.cc
echo "  translations_res.cc: $(stat -c%s /tmp/translations_res.cc) bytes"

# 3. 编译为共享库
echo ""
echo "[3/5] 编译共享库..."
g++ -shared -fPIC /tmp/translations_res.cc -o /tmp/libui_translations_override.so \
    $(pkg-config --cflags --libs Qt5Core)
echo "  libui_translations_override.so: $(stat -c%s /tmp/libui_translations_override.so) bytes"

# 复制到 openpilot 目录
cp /tmp/libui_translations_override.so "$BASEDIR/selfdrive/ui/libui_translations_override.so"

# 4. 修改 UI 启动方式，注入 LD_PRELOAD
echo ""
echo "[4/5] 配置 LD_PRELOAD 启动..."

# 备份原始 ui
if [ ! -f "$BASEDIR/selfdrive/ui/ui.real" ]; then
    cp "$BASEDIR/selfdrive/ui/ui" "$BASEDIR/selfdrive/ui/ui.real"
    echo "  已备份 ui -> ui.real"
else
    echo "  ui.real 已存在，跳过备份"
fi

# 创建 wrapper 脚本替代原始 ui
cat > "$BASEDIR/selfdrive/ui/ui" << 'WRAPPER'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
export LD_PRELOAD="$DIR/libui_translations_override.so"
exec "$DIR/ui.real" "$@"
WRAPPER
chmod +x "$BASEDIR/selfdrive/ui/ui"

echo "  wrapper 脚本已创建"

# 5. 清理
echo ""
echo "[5/5] 清理临时文件..."
rm -f /tmp/translations_res.cc /tmp/translations_assets.qrc /tmp/libui_translations_override.so
rm -f SConstruct 2>/dev/null
rm -rf site_scons/ 2>/dev/null
[ -f prebuilt.disabled ] && mv prebuilt.disabled prebuilt

echo ""
echo "========================================="
echo "  ✅ 完成！"
echo ""
echo "  重启以加载新翻译:"
echo "    sudo reboot"
echo ""
echo "  如需恢复原始 UI:"
echo "    cd /data/openpilot"
echo "    cp selfdrive/ui/ui.real selfdrive/ui/ui"
echo "    rm selfdrive/ui/libui_translations_override.so"
echo "    sudo reboot"
echo "========================================="
