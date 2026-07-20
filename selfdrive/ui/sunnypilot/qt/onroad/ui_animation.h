/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

#include <cmath>
#include <QColor>

/**
 * SmoothValue - 一阶 IIR 低通滤波器（浮点值平滑过渡）
 *
 * 与现有 smoothAEgo / leftBlinkerAlpha 同款算法，封装成可复用类。
 * 每帧调用 update()，value() 自动逼近 setTarget() 设定的目标值。
 *
 * alpha 参数指南（20fps 下）：
 *   0.25 → 4 帧完成过渡（快速响应，转向弧）
 *   0.15 → 8 帧完成过渡（中等速度，限速圆标缩放）
 *   0.12 → 12 帧完成过渡（平滑，ACC 颜色过渡）
 *   0.08 → 20 帧完成过渡（缓慢，呼吸脉冲）
 */
class SmoothValue {
public:
  explicit SmoothValue(float alpha = 0.15f) : alpha_(alpha), value_(0.0f), target_(0.0f) {}

  void setTarget(float target) { target_ = target; }
  void setAlpha(float alpha)   { alpha_ = alpha; }
  void setValue(float value)   { value_ = value; target_ = value; }  // 立即跳到目标值

  /// 每帧调用一次
  void update() {
    value_ += (target_ - value_) * alpha_;
  }

  float value() const { return value_; }
  float target() const { return target_; }
  bool settled(float threshold = 0.01f) const {
    return std::abs(target_ - value_) < threshold;
  }

private:
  float alpha_;
  float value_;
  float target_;
};


/**
 * SmoothColor - 颜色平滑过渡器
 *
 * 对 QColor 的 RGBA 四个通道分别做 IIR 滤波，实现颜色渐变动画。
 * 每帧调用 update()，color() 自动逼近 setTarget() 设定的目标颜色。
 */
class SmoothColor {
public:
  explicit SmoothColor(float alpha = 0.12f) : alpha_(alpha) {}

  void setTarget(const QColor &c) {
    target_ = c;
  }

  void setValue(const QColor &c) {
    r_ = c.red(); g_ = c.green(); b_ = c.blue(); a_ = c.alpha();
    target_ = c;
  }

  /// 每帧调用一次
  void update() {
    r_ += (target_.red()   - r_) * alpha_;
    g_ += (target_.green() - g_) * alpha_;
    b_ += (target_.blue()  - b_) * alpha_;
    a_ += (target_.alpha() - a_) * alpha_;
  }

  QColor color() const {
    return QColor((int)r_, (int)g_, (int)b_, (int)a_);
  }

  bool settled(float threshold = 2.0f) const {
    return std::abs(target_.red() - r_) < threshold &&
           std::abs(target_.green() - g_) < threshold &&
           std::abs(target_.blue() - b_) < threshold &&
           std::abs(target_.alpha() - a_) < threshold;
  }

private:
  float alpha_;
  float r_ = 0, g_ = 0, b_ = 0, a_ = 0;
  QColor target_;
};
