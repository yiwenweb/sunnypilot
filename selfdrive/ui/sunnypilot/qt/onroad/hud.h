/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

#include <array>
#include "selfdrive/ui/qt/onroad/hud.h"
#include "selfdrive/ui/sunnypilot/qt/onroad/developer_ui/developer_ui.h"

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
  void drawRoadName(QPainter &p, const QRect &surface_rect);
  void drawSteeringArc(QPainter &p, const QRect &surface_rect);
  void drawStandstillTimer(QPainter &p, const QRect &surface_rect);
  void drawDebugPlots(QPainter &p, const QRect &surface_rect);

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
  DebugPlotHistory steerHistory;
  DebugPlotHistory steerDesHistory;
  DebugPlotHistory speedHistory;
  DebugPlotHistory accelHistory;
  DebugPlotHistory torqueHistory;
};
