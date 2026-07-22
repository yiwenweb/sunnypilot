/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

#include <algorithm>
#include <array>
#include <cmath>
#include "selfdrive/ui/qt/onroad/hud.h"
#include "selfdrive/ui/sunnypilot/qt/onroad/developer_ui/developer_ui.h"
#include "selfdrive/ui/sunnypilot/qt/onroad/ui_animation.h"

struct DebugPlotHistory {
  static constexpr int SIZE = 100;
  std::array<float, SIZE> buf = {};
  int head = 0;

  void push(float v) { buf[head] = v; head = (head + 1) % SIZE; }
  float get(int i) const { return buf[(head + i) % SIZE]; }
  int count() const { return SIZE; }
};

class HudRendererSP : public HudRenderer {
  Q_OBJECT

public:
  HudRendererSP();
  void updateState(const UIState &s) override;
  void draw(QPainter &p, const QRect &surface_rect) override;

private:
  Params params;
  void drawText(QPainter &p, int x, int y, const QString &text, QColor color = Qt::white);
  void drawRightDevUI(QPainter &p, int x, int y);
  int drawRightDevUIElement(QPainter &p, int x, int y, const QString &value, const QString &label, const QString &units, QColor &color);
  int drawBottomDevUIElement(QPainter &p, int x, int y, const QString &value, const QString &label, const QString &units, QColor &color);
  void drawBottomDevUI(QPainter &p, int x, int y);
  void drawAccelBar(QPainter &p, const QRect &surface_rect);
  void drawTurnSignals(QPainter &p, const QRect &surface_rect);
  void drawSpeedLimit(QPainter &p, const QRect &surface_rect);
  void drawACCSetSpeedBox(QPainter &p, const QRect &surface_rect);
  void drawSpeedLimitCircle(QPainter &p, const QRect &surface_rect);
  void drawRoadName(QPainter &p, const QRect &surface_rect);
  void drawSteeringArc(QPainter &p, const QRect &surface_rect);
  void drawStandstillTimer(QPainter &p, const QRect &surface_rect);
  void drawDebugPlots(QPainter &p, const QRect &surface_rect);
  void drawLaneLineData(QPainter &p, const QRect &surface_rect);
  void drawSCC(QPainter &p);

  // ===== 三层景深绘制 =====
  enum class GlassLevel {
    L1_Primary,    // 前景：关键信息（速度、ACC、限速）
    L2_Secondary,  // 中景：辅助信息（车道线距离、转向弧）
    L3_Tertiary,   // 背景：调试/次要信息
  };
  void drawGlassBox(QPainter &p, const QRect &rect, int corner_radius, GlassLevel level);

  bool lead_status;
  float lead_d_rel;
  float lead_v_rel;
  bool torqueLateral;
  float angleSteers;
  float angleSteersDesired;
  float desiredCurvature;
  float curvature;
  float roll;
  int memoryUsagePercent;
  int devUiInfo;
  float gpsAccuracy;
  float altitude;
  float vEgo;
  float aEgo;
  float smoothAEgo;
  float steeringTorqueEps;
  // bool lkasPrepared;  // TODO: cereal CarState lacks lkasPrepared in qt-dev
  float bearingAccuracyDeg;
  float bearingDeg;
  bool torquedUseParams;
  float latAccelFactorFiltered;
  float frictionCoefficientFiltered;
  bool liveValid;
  QString speedUnit;
  bool latActive;
  bool steerOverride;
  bool reversing;
  bool accelBarEnabled;
  bool turnSignalEnabled;
  bool leftBlinker;
  bool rightBlinker;
  bool speedLimitEnabled;
  bool roadNameEnabled;
  bool speedLimitValid;
  float speedLimit;
  bool speedLimitAheadValid;
  float speedLimitAhead;
  QString roadName;
  bool steeringArcEnabled;
  bool standstillTimerEnabled;
  int standstillSeconds;
  bool isStandstill;
  cereal::CarParams::SteerControlType steerControlType;
  cereal::CarControl::Actuators::Reader actuators;
  bool debugPlotsEnabled;
  bool laneLineDataEnabled;
  bool sccVisionEnabled;
  bool sccVisionActive;
  bool sccMapEnabled;
  bool sccMapActive;
  bool longOverride;
  DebugPlotHistory steerHistory;
  DebugPlotHistory steerDesHistory;
  DebugPlotHistory speedHistory;
  DebugPlotHistory accelHistory;
  DebugPlotHistory torqueHistory;

  // MICI-style smoothing filters
  float smoothSteerDisplay = 0.0f;
  float smoothSteerDesiredDisplay = 0.0f;
  float leftBlinkerAlpha = 0.0f;
  float rightBlinkerAlpha = 0.0f;
  float leftLaneDist = 0.0f;
  float rightLaneDist = 0.0f;

  // Speed limit circle cache (performance optimization for scheme B)
  QPixmap speedLimitCircleCache;
  int cachedSpeedLimit = -1;
  bool speedLimitCacheDirty = true;

  // Speed limit parameters
  int speedLimitStyle = 1;  // 0=rect, 1=circle, 2=large circle
  bool speedLimitColorMAX = true;
  bool speedLimitShowSource = false;
  int speedLimitWarnThreshold = 10;
  int speedLimitDangerThreshold = 20;
  float speedLimitConfidence = 1.0f;

  // ===== P1: 平滑动画成员 =====
  // ACC 方框 MAX 标签颜色平滑过渡
  SmoothColor smoothMaxColor{0.12f};
  SmoothColor smoothSetSpeedColor{0.12f};
  // 限速圆标出现/消失动画
  SmoothValue speedLimitScale{0.15f};
  SmoothValue speedLimitOpacity{0.15f};
  // 转向灯呼吸脉冲
  SmoothValue turnSignalPulse{0.08f};

  // ===== P2: 转向弧颜色平滑过渡 =====
  SmoothColor smoothArcColor{0.15f};
  SmoothColor smoothArcDiamondColor{0.15f};
};
