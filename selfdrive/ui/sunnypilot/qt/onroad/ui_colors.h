/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

#include <QColor>
#include <QLinearGradient>

/**
 * SPColor - sunnypilot 语义化色彩系统
 *
 * 所有 HUD 元素颜色统一定义，消除散落在代码各处的硬编码 QColor。
 * 按功能分为：品牌色、语义状态色、三层景深背景色、文字色、功能元素色。
 */
namespace SPColor {

// ============================================================
// 品牌色（sunnypilot 主色）
// ============================================================
inline const QColor Primary        = QColor(0, 168, 255);        // 科技蓝
inline const QColor PrimaryDim     = QColor(0, 168, 255, 120);   // 半透明蓝
inline const QColor PrimaryGlow    = QColor(0, 168, 255, 60);    // 外发光蓝

// ============================================================
// 语义状态色（状态反馈）
// ============================================================
inline const QColor Success        = QColor(0, 220, 130);        // 激活/正常/未超速
inline const QColor SuccessDim     = QColor(0, 220, 130, 140);   // 半透明成功
inline const QColor Warning        = QColor(255, 180, 40);       // 警告/轻微超速
inline const QColor WarningDim     = QColor(255, 180, 40, 140);  // 半透明警告
inline const QColor Danger         = QColor(255, 70, 70);        // 危险/严重超速
inline const QColor DangerDim      = QColor(255, 70, 70, 140);   // 半透明危险
inline const QColor Neutral        = QColor(160, 170, 180);      // 未激活/次要/手动模式
inline const QColor NeutralDim     = QColor(160, 170, 180, 100); // 半透明中性

// ============================================================
// HUD 背景色（三层景深模型）
// ============================================================
// L1 前景：关键信息（速度、ACC、限速）——近乎实心，最高对比度
inline const QColor BgL1           = QColor(10, 10, 12, 220);    // 深空黑，87% 不透明
inline const QColor BgL1Border     = QColor(255, 255, 255, 0);   // 无边框（靠对比度分离）

// L2 中景：辅助信息（车道线距离、转向弧）——半透明，轻微蓝调
inline const QColor BgL2           = QColor(20, 22, 28, 160);    // 63% 不透明
inline const QColor BgL2Border     = QColor(255, 255, 255, 30);  // 1px 微边框

// L3 背景：调试/次要信息（调试曲线、Dev UI）——高度透明
inline const QColor BgL3           = QColor(30, 34, 42, 100);    // 39% 不透明
inline const QColor BgL3Border     = QColor(255, 255, 255, 0);   // 无边框

// 兼容旧代码的通用背景色
inline const QColor HudBg          = QColor(0, 0, 0, 166);       // 原 ACC 方框背景
inline const QColor HudBgBorder    = QColor(255, 255, 255, 75);  // 原 ACC 方框边框
inline const QColor DevUiBg        = QColor(0, 0, 0, 100);       // 原 Dev UI 底部背景
inline const QColor DebugPlotBg    = QColor(0, 0, 0, 150);       // 原调试曲线背景

// ============================================================
// 文字色（四级层次）
// ============================================================
inline const QColor TextPrimary    = QColor(255, 255, 255);       // 主文字（数值、标题）
inline const QColor TextSecondary  = QColor(200, 205, 210);      // 次要文字（标签、单位）
inline const QColor TextTertiary   = QColor(140, 145, 155);      // 辅助文字（说明、来源）
inline const QColor TextDisabled   = QColor(100, 105, 110);      // 禁用文字
inline const QColor TextGhost      = QColor(255, 255, 255, 180); // 幽灵文字（原道路名称）

// ============================================================
// 功能元素色（特定 HUD 元素）
// ============================================================
// AccelBar 加速度条
inline const QColor AccelGreen     = QColor(0, 230, 120);        // 加速绿
inline const QColor AccelYellow    = QColor(255, 220, 0);        // 高加速黄
inline const QColor DecelRed       = QColor(255, 80, 60);        // 减速红
inline const QColor DecelOrange    = QColor(255, 140, 40);       // 高减速橙

// 转向灯
inline const QColor TurnSignal     = QColor(0, 255, 90);         // 转向灯绿
inline const QColor TurnSignalGlow = QColor(0, 220, 80, 60);     // 转向灯发光

// 车道线距离
inline const QColor LaneLeft       = QColor(100, 180, 255);      // 左车道线浅蓝
inline const QColor LaneRight      = QColor(120, 255, 160);      // 右车道线浅绿

// 限速标志
inline const QColor SpeedLimit     = QColor(220, 30, 30);        // 维也纳公约红
inline const QColor SpeedLimitBg   = QColor(255, 255, 255, 250); // 限速白底
inline const QColor SpeedLimitText = QColor(30, 30, 30);         // 限速黑字

// 前方限速提示
inline const QColor AheadDecrease  = QColor(255, 180, 60);       // 降速橙
inline const QColor AheadIncrease  = QColor(120, 200, 255);      // 提速蓝

// 转向弧
inline const QColor ArcActive      = QColor(255, 255, 255);      // 激活白
inline const QColor ArcInactive    = QColor(180, 180, 180, 240); // 未激活灰
inline const QColor ArcBackground  = QColor(255, 255, 255, 45);  // 背景弧

// 停车计时器
inline const QColor TimerText      = QColor(100, 220, 255);      // 计时器青蓝
inline const QColor TimerIcon      = QColor(255, 255, 255, 180); // 计时器图标

// ACC MAX 标签（原色板，用于状态机）
inline const QColor MaxDefault     = QColor(0xa6, 0xa6, 0xa6);   // 默认灰
inline const QColor MaxDisengaged  = QColor(255, 255, 255);      // 未激活白
inline const QColor MaxOverride    = QColor(0x91, 0x9b, 0x95);   // 覆盖灰绿
inline const QColor MaxEngaged     = QColor(0x80, 0xd8, 0xa6);   // 激活绿
inline const QColor MaxSpeedGood   = QColor(0x80, 0xd8, 0xa6);   // 未超速绿
inline const QColor MaxSpeedWarn   = QColor(255, 165, 0);        // 中度超速橙
inline const QColor MaxSpeedDanger = QColor(255, 60, 60);        // 严重超速红
inline const QColor SetSpeedUnset  = QColor(0x72, 0x72, 0x72);   // 未设定灰

// ============================================================
// 调试曲线
// ============================================================
inline const QColor PlotBlue       = QColor(80, 160, 255);       // 实际值蓝
inline const QColor PlotGreen      = QColor(80, 255, 140);       // 目标值绿
inline const QColor PlotOrange     = QColor(255, 180, 60);       // EPS 扭矩橙
inline const QColor PlotGrid       = QColor(255, 255, 255, 60);  // 网格线
inline const QColor PlotLabel      = QColor(200, 200, 200, 180); // 标题
inline const QColor PlotAxis       = QColor(180, 180, 180, 150); // 轴标签
inline const QColor PlotUnit       = QColor(160, 160, 160, 140); // 单位

// ============================================================
// 工具函数
// ============================================================

/// 创建垂直渐变（上 → 下）
inline QLinearGradient makeVerticalGradient(const QColor &top, const QColor &bottom,
                                             qreal y0, qreal y1) {
  QLinearGradient g(0, y0, 0, y1);
  g.setColorAt(0, top);
  g.setColorAt(1, bottom);
  return g;
}

/// 创建水平渐变（左 → 右）
inline QLinearGradient makeHorizontalGradient(const QColor &left, const QColor &right,
                                               qreal x0, qreal x1) {
  QLinearGradient g(x0, 0, x1, 0);
  g.setColorAt(0, left);
  g.setColorAt(1, right);
  return g;
}

/// 颜色插值（t: 0.0 ~ 1.0）
inline QColor lerp(const QColor &a, const QColor &b, float t) {
  t = qBound(0.0f, t, 1.0f);
  return QColor(
    a.red()   + (int)((b.red()   - a.red())   * t),
    a.green() + (int)((b.green() - a.green()) * t),
    a.blue()  + (int)((b.blue()  - a.blue())  * t),
    a.alpha() + (int)((b.alpha() - a.alpha()) * t)
  );
}

/// 调整透明度（保持 RGB 不变）
inline QColor withAlpha(const QColor &c, int alpha) {
  return QColor(c.red(), c.green(), c.blue(), qBound(0, alpha, 255));
}

/// 降低亮度（factor: 0.0 ~ 1.0）
inline QColor darker(const QColor &c, float factor) {
  return QColor::fromRgbF(
    c.redF()   * factor,
    c.greenF() * factor,
    c.blueF()  * factor,
    c.alphaF()
  );
}

/// 提高亮度（factor: 1.0 ~ 2.0）
inline QColor lighter(const QColor &c, float factor) {
  return QColor::fromRgbF(
    qMin(1.0, c.redF()   * factor),
    qMin(1.0, c.greenF() * factor),
    qMin(1.0, c.blueF()  * factor),
    c.alphaF()
  );
}

} // namespace SPColor
