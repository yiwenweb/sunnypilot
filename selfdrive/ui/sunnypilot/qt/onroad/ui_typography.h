/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

#include <QFont>
#include "selfdrive/ui/qt/util.h"

/**
 * SPFont - sunnypilot 排版系统
 *
 * 基于 1.25x Major Third 比例的字号阶梯，消除散落在代码中的随机字号。
 * 字重从 Light 到 Black 六档，提供精细的视觉层次。
 *
 * 字号阶梯（基准 16px 设置面板正文）：
 *   Caption  = 20pt  → 辅助说明
 *   Body     = 25pt  → 正文/标签
 *   Title    = 31pt  → 小标题/数据标签
 *   Headline = 39pt  → 大标题/MAX 标签
 *   Display  = 49pt  → 限速数字
 *   Hero     = 61pt  → ACC 设定速度
 *   Giant    = 76pt  → 当前速度
 *   Massive  = 95pt  → 停车计时器
 */
namespace SPFont {

// ============================================================
// 字号比例：1.25x Major Third
// ============================================================
enum Scale {
  Caption  = 20,   // 16 × 1.25 = 20   辅助说明、来源标注
  Body     = 25,   // 20 × 1.25 = 25   正文、数据标签、单位
  Title    = 31,   // 25 × 1.25 ≈ 31   小标题、数据数值
  Headline = 39,   // 31 × 1.25 ≈ 39   大标题、MAX 标签
  Display  = 49,   // 39 × 1.25 ≈ 49   限速圆标数字
  Hero     = 61,   // 49 × 1.25 ≈ 61   ACC 设定速度
  Giant    = 76,   // 61 × 1.25 ≈ 76   当前速度（主视觉焦点）
  Massive  = 95,   // 76 × 1.25 = 95   停车计时器
};

// ============================================================
// 字重（六档精细层次）
// ============================================================
inline QFont light(int size)    { return InterFont(size, QFont::Light); }
inline QFont regular(int size)  { return InterFont(size, QFont::Normal); }
inline QFont medium(int size)   { return InterFont(size, QFont::Medium); }
inline QFont semibold(int size) { return InterFont(size, QFont::DemiBold); }
inline QFont bold(int size)     { return InterFont(size, QFont::Bold); }
inline QFont black(int size)    { return InterFont(size, QFont::Black); }

// ============================================================
// HUD 专用快捷组合
// ============================================================

/// 当前速度（屏幕中央最大数字）
inline QFont hudSpeed()         { return black(Giant); }

/// 速度单位（km/h / mph）
inline QFont hudSpeedUnit()     { return regular(Title); }

/// ACC 设定速度（方框内大数字）
inline QFont hudSetSpeed()      { return bold(Hero); }

/// ACC "MAX" 标签
inline QFont hudSetSpeedLabel() { return semibold(Headline); }

/// 限速圆标数字
inline QFont speedLimitNumber() { return bold(Display); }

/// 前方限速提示（▼ 60 / ▲ 100）
inline QFont speedLimitAhead()  { return bold(Body); }

/// "LIMIT" 标签
inline QFont speedLimitLabel()  { return medium(Caption); }

/// 道路名称
inline QFont roadName()         { return regular(56); }  // 保持原 56pt

/// 数据标签（"左边" / "右边" / "模型" / "实际"）
inline QFont dataLabel()        { return regular(Body); }

/// 数据数值（"1.25m" / "0.8Nm"）
inline QFont dataValue()        { return bold(Title); }

/// Dev UI 标签
inline QFont devUiLabel()       { return regular(Body); }

/// Dev UI 数值
inline QFont devUiValue()       { return bold(Title); }

/// 底部 Dev UI 标签+数值
inline QFont bottomDevUi()      { return semibold(38); }  // 保持原 38pt

/// 调试曲线标题
inline QFont debugPlotTitle()   { return regular(28); }

/// 调试曲线轴标签
inline QFont debugPlotAxis()    { return regular(24); }

/// 调试曲线单位
inline QFont debugPlotUnit()    { return regular(Caption); }

/// 停车计时器图标
inline QFont timerIcon()        { return regular(152); }

/// 停车计时器时间
inline QFont timerTime()        { return bold(176); }

/// 转向弧（不使用字体，仅作记录）
// 转向弧是图形元素，不涉及字体

} // namespace SPFont
