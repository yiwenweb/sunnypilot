#!/bin/bash
# ============================================================
# 在 C3 上重编译翻译资源并生成覆盖库
#
# 原理: 用 rcc 把新的 .qm 编译成 C++ 源码，再编译成共享库。
#       manager 启动 UI 时自动通过 LD_PRELOAD 加载，覆盖内嵌的旧翻译。
#       (逻辑在 system/manager/process.py 的 nativelauncher 中)
#
# 用法: SSH 到 C3:
#   cd /data/openpilot
#   bash sunnypilot/scripts/rebuild_ui_translations.sh
# ============================================================
set -e
BASEDIR="/data/openpilot"
cd "$BASEDIR"

echo "=== 重编译翻译资源 ==="

TR_DIR="$BASEDIR/selfdrive/ui/translations"
OUTPUT_SO="$BASEDIR/selfdrive/ui/libui_translations_override.so"

echo "[1/4] 检查 .qm 文件..."
echo "  zh-CHS.qm: $(stat -c%s "$TR_DIR/main_zh-CHS.qm" 2>/dev/null || echo '不存在') bytes"
echo "  .ts 未翻译: $(grep -c 'type="unfinished"' "$TR_DIR/main_zh-CHS.ts" 2>/dev/null || echo 0)"

# 如果之前有 wrapper 脚本方案的残留，恢复原始 ui
if [ -f "$BASEDIR/selfdrive/ui/ui.real" ]; then
    echo "  检测到旧方案残留，恢复原始 ui..."
    cp "$BASEDIR/selfdrive/ui/ui.real" "$BASEDIR/selfdrive/ui/ui"
    rm -f "$BASEDIR/selfdrive/ui/ui.real"
    echo "  已恢复"
fi

echo ""
echo "[2/4] 生成资源 C++ 源码..."

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

echo ""
echo "[3/4] 编译共享库..."
g++ -shared -fPIC /tmp/translations_res.cc -o "$OUTPUT_SO" \
    $(pkg-config --cflags --libs Qt5Core)
echo "  libui_translations_override.so: $(stat -c%s "$OUTPUT_SO") bytes"

echo ""
echo "[4/4] 清理临时文件..."
rm -f /tmp/translations_res.cc /tmp/translations_assets.qrc

echo ""
echo "========================================="
echo "  ✅ 完成！"
echo ""
echo "  翻译覆盖库已生成: $OUTPUT_SO"
echo "  manager 启动 UI 时会自动通过 LD_PRELOAD 加载"
echo ""
echo "  重启以加载新翻译:"
echo "    sudo reboot"
echo ""
echo "  如需移除翻译覆盖:"
echo "    rm $OUTPUT_SO"
echo "    sudo reboot"
echo "========================================="
