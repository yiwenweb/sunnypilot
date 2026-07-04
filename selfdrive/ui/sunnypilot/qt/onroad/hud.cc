/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/onroad/hud.h"

#include "selfdrive/ui/qt/util.h"


HudRendererSP::HudRendererSP() {}

void HudRendererSP::updateState(const UIState &s) {
  HudRenderer::updateState(s);

  const SubMaster &sm = *(s.sm);
  const bool cs_alive = sm.alive("controlsState");
  const auto cs = sm["controlsState"].getControlsState();
  const auto car_state = sm["carState"].getCarState();
  const auto car_control = sm["carControl"].getCarControl();
  const auto radar_state = sm["radarState"].getRadarState();
  const auto is_gps_location_external = sm.rcv_frame("gpsLocationExternal") > 1;
  const auto gpsLocation = is_gps_location_external ? sm["gpsLocationExternal"].getGpsLocationExternal() : sm["gpsLocation"].getGpsLocation();
  const auto ltp = sm["liveTorqueParameters"].getLiveTorqueParameters();
  const auto car_params = sm["carParams"].getCarParams();

  static int reverse_delay = 0;
  bool reverse_allowed = false;
  if (int(car_state.getGearShifter()) != 4) {
    reverse_delay = 0;
    reverse_allowed = false;
  } else {
    reverse_delay += 50;
    if (reverse_delay >= 1000) {
      reverse_allowed = true;
    }
  }

  reversing = reverse_allowed;
  is_metric = s.scene.is_metric;

  // Handle older routes where vEgoCluster is not set
  v_ego_cluster_seen = v_ego_cluster_seen || car_state.getVEgoCluster() != 0.0;
  float v_ego = v_ego_cluster_seen ? car_state.getVEgoCluster() : car_state.getVEgo();
  speed = cs_alive ? std::max<float>(0.0, v_ego) : 0.0;
  speed *= is_metric ? MS_TO_KPH : MS_TO_MPH;

  latActive = car_control.getLatActive();
  steerOverride = car_state.getSteeringPressed();

  devUiInfo = s.scene.dev_ui_info;

  speedUnit = is_metric ? tr("km/h") : tr("mph");
  lead_d_rel = radar_state.getLeadOne().getDRel();
  lead_v_rel = radar_state.getLeadOne().getVRel();
  lead_status = radar_state.getLeadOne().getStatus();
  steerControlType = car_params.getSteerControlType();
  actuators = car_control.getActuators();
  torqueLateral = steerControlType == cereal::CarParams::SteerControlType::TORQUE;
  angleSteers = car_state.getSteeringAngleDeg();
  angleSteersDesired = cs.getSteeringAngleDesiredDeg();
  desiredCurvature = cs.getDesiredCurvature();
  curvature = cs.getCurvature();
  roll = sm["liveParameters"].getLiveParameters().getRoll();
  memoryUsagePercent = sm["deviceState"].getDeviceState().getMemoryUsagePercent();
  gpsAccuracy = is_gps_location_external ? gpsLocation.getHorizontalAccuracy() : 1.0;  // External reports accuracy, internal does not.
  altitude = gpsLocation.getAltitude();
  vEgo = car_state.getVEgo();
  aEgo = car_state.getAEgo();
  // IIR smoothing filter for AccelBar (matches 2026 RocketFuel smoothness)
  smoothAEgo += (aEgo - smoothAEgo) * 0.2f;
  steeringTorqueEps = car_state.getSteeringTorqueEps();
  bearingAccuracyDeg = gpsLocation.getBearingAccuracyDeg();
  bearingDeg = gpsLocation.getBearingDeg();
  torquedUseParams = ltp.getUseParams();
  latAccelFactorFiltered = ltp.getLatAccelFactorFiltered();
  frictionCoefficientFiltered = ltp.getFrictionCoefficientFiltered();
  liveValid = ltp.getLiveValid();
  accelBarEnabled = s.scene.accel_bar;
  turnSignalEnabled = s.scene.turn_signal;
  leftBlinker = car_state.getLeftBlinker();
  rightBlinker = car_state.getRightBlinker();
  speedLimitEnabled = s.scene.speed_limit;
  roadNameEnabled = s.scene.road_name;

  // LiveMapDataSP
  if (sm.rcv_frame("liveMapDataSP") > 0) {
    auto live_map = sm["liveMapDataSP"].getLiveMapDataSP();
    speedLimitValid = live_map.getSpeedLimitValid();
    speedLimit = live_map.getSpeedLimit();
    speedLimitAheadValid = live_map.getSpeedLimitAheadValid();
    speedLimitAhead = live_map.getSpeedLimitAhead();
    roadName = QString::fromStdString(live_map.getRoadName());
  } else {
    speedLimitValid = false;
    roadName.clear();
  }
  steeringArcEnabled = s.scene.steering_arc;
  standstillTimerEnabled = s.scene.standstill_timer;

  // Standstill timer: track when speed is 0 and count seconds
  static uint64_t standstill_start = 0;
  static uint64_t last_standstill_frame = 0;
  if (speed < 0.5f) {  // nearly stopped
    if (standstill_start == 0) standstill_start = millis_since_boot();
    uint64_t now = millis_since_boot();
    if (now - last_standstill_frame >= 1000) {
      standstillSeconds = (now - standstill_start) / 1000;
      last_standstill_frame = now;
    }
    isStandstill = true;
  } else {
    standstill_start = 0;
    standstillSeconds = 0;
    last_standstill_frame = 0;
    isStandstill = false;
  }
}

void HudRendererSP::draw(QPainter &p, const QRect &surface_rect) {
  HudRenderer::draw(p, surface_rect);
  if (!reversing) {
    // AccelBar at bottom center
    if (accelBarEnabled) {
      drawAccelBar(p, surface_rect);
    }

    // Turn signal indicators (left/right sides)
    if (turnSignalEnabled) {
      drawTurnSignals(p, surface_rect);
    }

    // Speed limit sign (near set speed)
    if (speedLimitEnabled && speedLimitValid) {
      drawSpeedLimit(p, surface_rect);
    }

    // Road name (top center)
    if (roadNameEnabled && !roadName.isEmpty()) {
      drawRoadName(p, surface_rect);
    }

    // Steering arc (bottom)
    if (steeringArcEnabled) {
      drawSteeringArc(p, surface_rect);
    }

    // Standstill timer (bottom-right corner)
    if (standstillTimerEnabled && isStandstill && standstillSeconds > 0) {
      drawStandstillTimer(p, surface_rect);
    }

    // Bottom Dev UI
    if (devUiInfo == 2) {
      QRect rect_bottom(surface_rect.left(), surface_rect.bottom() - 60, surface_rect.width(), 61);
      p.setPen(Qt::NoPen);
      p.setBrush(QColor(0, 0, 0, 100));
      p.drawRect(rect_bottom);
      drawBottomDevUI(p, rect_bottom.left(), rect_bottom.center().y());
    }

    // Right Dev UI
    if (devUiInfo != 0) {
      QRect rect_right(surface_rect.right() - (UI_BORDER_SIZE * 2), UI_BORDER_SIZE * 1.5, 184, 170);
      drawRightDevUI(p, surface_rect.right() - 184 - UI_BORDER_SIZE * 2, UI_BORDER_SIZE * 2 + rect_right.height());
    }
  }
}

void HudRendererSP::drawText(QPainter &p, int x, int y, const QString &text, QColor color) {
  QRect real_rect = p.fontMetrics().boundingRect(text);
  real_rect.moveCenter({x, y - real_rect.height() / 2});
  p.setPen(color);
  p.drawText(real_rect.x(), real_rect.bottom(), text);
}

int HudRendererSP::drawRightDevUIElement(QPainter &p, int x, int y, const QString &value, const QString &label, const QString &units, QColor &color) {

  p.setFont(InterFont(28, QFont::Bold));
  x += 92;
  y += 80;
  drawText(p, x, y, label);

  p.setFont(InterFont(30 * 2, QFont::Bold));
  y += 65;
  drawText(p, x, y, value, color);

  p.setFont(InterFont(28, QFont::Bold));

  if (units.length() > 0) {
    p.save();
    x += 120;
    y -= 25;
    p.translate(x, y);
    p.rotate(-90);
    drawText(p, 0, 0, units);
    p.restore();
  }

  return 130;
}

void HudRendererSP::drawRightDevUI(QPainter &p, int x, int y) {
  int rh = 5;
  int ry = y;

  UiElement dRelElement = DeveloperUi::getDRel(lead_status, lead_d_rel);
  rh += drawRightDevUIElement(p, x, ry, dRelElement.value, dRelElement.label, dRelElement.units, dRelElement.color);
  ry = y + rh;

  UiElement vRelElement = DeveloperUi::getVRel(lead_status, lead_v_rel, is_metric, speedUnit);
  rh += drawRightDevUIElement(p, x, ry, vRelElement.value, vRelElement.label, vRelElement.units, vRelElement.color);
  ry = y + rh;

  UiElement steeringAngleDegElement = DeveloperUi::getSteeringAngleDeg(angleSteers, latActive, steerOverride);
  rh += drawRightDevUIElement(p, x, ry, steeringAngleDegElement.value, steeringAngleDegElement.label, steeringAngleDegElement.units, steeringAngleDegElement.color);
  ry = y + rh;

  UiElement actuatorsOutputLateralElement = DeveloperUi::getActuatorsOutputLateral(steerControlType, actuators, desiredCurvature, vEgo, roll, latActive, steerOverride);
  rh += drawRightDevUIElement(p, x, ry, actuatorsOutputLateralElement.value, actuatorsOutputLateralElement.label, actuatorsOutputLateralElement.units, actuatorsOutputLateralElement.color);
  ry = y + rh;

  UiElement actualLateralAccelElement = DeveloperUi::getActualLateralAccel(curvature, vEgo, roll, latActive, steerOverride);
  rh += drawRightDevUIElement(p, x, ry, actualLateralAccelElement.value, actualLateralAccelElement.label, actualLateralAccelElement.units, actualLateralAccelElement.color);
  ry = y + rh;

  UiElement steerDesiredElement = DeveloperUi::getSteeringAngleDesiredDeg(latActive, angleSteersDesired, angleSteers);
  rh += drawRightDevUIElement(p, x, ry, steerDesiredElement.value, steerDesiredElement.label, steerDesiredElement.units, steerDesiredElement.color);
}

int HudRendererSP::drawBottomDevUIElement(QPainter &p, int x, int y, const QString &value, const QString &label, const QString &units, QColor &color) {
  p.setFont(InterFont(38, QFont::Bold));
  QFontMetrics fm(p.font());
  QRect init_rect = fm.boundingRect(label + " ");
  QRect real_rect = fm.boundingRect(init_rect, 0, label + " ");
  real_rect.moveCenter({x, y});

  QRect init_rect2 = fm.boundingRect(value);
  QRect real_rect2 = fm.boundingRect(init_rect2, 0, value);
  real_rect2.moveTop(real_rect.top());
  real_rect2.moveLeft(real_rect.right() + 10);

  QRect init_rect3 = fm.boundingRect(units);
  QRect real_rect3 = fm.boundingRect(init_rect3, 0, units);
  real_rect3.moveTop(real_rect.top());
  real_rect3.moveLeft(real_rect2.right() + 10);

  p.setPen(Qt::white);
  p.drawText(real_rect, Qt::AlignLeft | Qt::AlignVCenter, label);

  p.setPen(color);
  p.drawText(real_rect2, Qt::AlignRight | Qt::AlignVCenter, value);
  p.drawText(real_rect3, Qt::AlignLeft | Qt::AlignVCenter, units);
  return 430;
}

void HudRendererSP::drawBottomDevUI(QPainter &p, int x, int y) {
  int rw = 90;

  UiElement aEgoElement = DeveloperUi::getAEgo(aEgo);
  rw += drawBottomDevUIElement(p, rw, y, aEgoElement.value, aEgoElement.label, aEgoElement.units, aEgoElement.color);

  UiElement vEgoLeadElement = DeveloperUi::getVEgoLead(lead_status, lead_v_rel, vEgo, is_metric, speedUnit);
  rw += drawBottomDevUIElement(p, rw, y, vEgoLeadElement.value, vEgoLeadElement.label, vEgoLeadElement.units, vEgoLeadElement.color);

  if (torqueLateral && torquedUseParams) {
    UiElement frictionCoefficientFilteredElement = DeveloperUi::getFrictionCoefficientFiltered(frictionCoefficientFiltered, liveValid);
    rw += drawBottomDevUIElement(p, rw, y, frictionCoefficientFilteredElement.value, frictionCoefficientFilteredElement.label, frictionCoefficientFilteredElement.units, frictionCoefficientFilteredElement.color);

    UiElement latAccelFactorFilteredElement = DeveloperUi::getLatAccelFactorFiltered(latAccelFactorFiltered, liveValid);
    rw += drawBottomDevUIElement(p, rw, y, latAccelFactorFilteredElement.value, latAccelFactorFilteredElement.label, latAccelFactorFilteredElement.units, latAccelFactorFilteredElement.color);
  } else {
    UiElement steeringTorqueEpsElement = DeveloperUi::getSteeringTorqueEps(steeringTorqueEps);
    rw += drawBottomDevUIElement(p, rw, y, steeringTorqueEpsElement.value, steeringTorqueEpsElement.label, steeringTorqueEpsElement.units, steeringTorqueEpsElement.color);

    UiElement bearingDegElement = DeveloperUi::getBearingDeg(bearingAccuracyDeg, bearingDeg);
    rw += drawBottomDevUIElement(p, rw, y, bearingDegElement.value, bearingDegElement.label, bearingDegElement.units, bearingDegElement.color);
  }

  UiElement altitudeElement = DeveloperUi::getAltitude(gpsAccuracy, altitude);
  rw += drawBottomDevUIElement(p, rw, y, altitudeElement.value, altitudeElement.label, altitudeElement.units, altitudeElement.color);
}

void HudRendererSP::drawAccelBar(QPainter &p, const QRect &surface_rect) {
  // RocketFuel: vertical bar on the left side (ported from sunnypilot 2026)
  // Green fills UP for acceleration, red fills DOWN for deceleration
  const int bar_width = 36;
  const int bar_height = 280;
  const float max_accel = 3.0f;  // m/s^2
  const int margin_left = 20;

  int track_x = margin_left;
  int track_y = surface_rect.center().y() - bar_height / 2;

  // Background track (dark rounded rect)
  p.setPen(Qt::NoPen);
  p.setBrush(QColor(0, 0, 0, 100));
  p.drawRoundedRect(track_x, track_y, bar_width, bar_height, bar_width / 2, bar_width / 2);

  // Center zero line
  int center_y = track_y + bar_height / 2;
  p.setPen(QPen(QColor(255, 255, 255, 70), 1));
  p.drawLine(track_x + 4, center_y, track_x + bar_width - 4, center_y);

  // Filled portion
  float accel_val = std::clamp(smoothAEgo, -max_accel, max_accel);
  int fill_height = (int)(std::abs(accel_val) / max_accel * (bar_height / 2 - 4));

  if (fill_height > 1) {
    QColor color;
    int fill_y;
    if (accel_val >= 0) {
      // Acceleration: green, fills upward from center
      color = QColor(0, 210, 90, 200);
      fill_y = center_y - fill_height;
    } else {
      // Deceleration: red, fills downward from center
      color = QColor(230, 55, 55, 200);
      fill_y = center_y;
    }

    p.setPen(Qt::NoPen);
    p.setBrush(color);
    p.drawRoundedRect(track_x + 4, fill_y, bar_width - 8, fill_height, 6, 6);
  }
}

void HudRendererSP::drawTurnSignals(QPainter &p, const QRect &surface_rect) {
  // 2026-style turn signal indicators on left and right sides
  const int arrow_size = 55;
  const int margin = 40;
  int cy = surface_rect.center().y();

  auto drawArrow = [&](int cx, int cy, bool pointingLeft, bool active) {
    if (!active) return;

    // Glow background
    p.save();
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(0, 220, 80, 60));
    p.drawEllipse(QPoint(cx, cy), arrow_size, arrow_size * 2 / 3);

    // Arrow body
    QPainterPath arrow;
    int dir = pointingLeft ? -1 : 1;

    // Triangle points
    QPointF tip(cx + dir * arrow_size * 0.7, cy);
    QPointF base1(cx - dir * arrow_size * 0.3, cy - arrow_size * 0.5);
    QPointF base2(cx - dir * arrow_size * 0.3, cy + arrow_size * 0.5);

    // Arrow head (triangle)
    arrow.moveTo(tip);
    arrow.lineTo(base1);
    arrow.lineTo(base2);
    arrow.closeSubpath();

    // Arrow stem (thin rectangle)
    QRectF stem(cx - dir * arrow_size * 0.6, cy - arrow_size * 0.15,
                arrow_size * 0.6, arrow_size * 0.3);

    p.setPen(Qt::NoPen);
    p.setBrush(QColor(0, 255, 90, 220));
    p.drawPath(arrow);
    p.drawRoundedRect(stem, 3, 3);

    p.restore();
  };

  drawArrow(margin + arrow_size / 2, cy, true, leftBlinker);
  drawArrow(surface_rect.right() - margin - arrow_size / 2, cy, false, rightBlinker);
}

void HudRendererSP::drawSpeedLimit(QPainter &p, const QRect &surface_rect) {
  // 2026-style speed limit sign (Vienna convention: white circle, red border)
  const int sign_size = 90;
  int cx = surface_rect.right() - sign_size - UI_BORDER_SIZE * 3;
  int cy = surface_rect.top() + UI_BORDER_SIZE * 2 + sign_size / 2;

  // Convert speed from m/s
  int limit_kmh = (int)(speedLimit * (is_metric ? 3.6f : 2.237f));
  QString text = QString::number(limit_kmh);

  // Draw sign background (white circle with red border)
  p.save();
  p.setPen(QPen(QColor(200, 40, 40), 8));
  p.setBrush(QColor(255, 255, 255, 245));
  p.drawEllipse(QPoint(cx, cy), sign_size / 2, sign_size / 2);

  // Speed number
  p.setPen(QColor(30, 30, 30));
  p.setFont(InterFont(sign_size / 2, QFont::Bold));
  QFontMetrics fm(p.font());
  QRect text_rect = fm.boundingRect(text);
  text_rect.moveCenter(QPoint(cx, cy));
  p.drawText(text_rect, Qt::AlignCenter, text);

  // Speed limit ahead (smaller sign below)
  if (speedLimitAheadValid) {
    int ahead_kmh = (int)(speedLimitAhead * (is_metric ? 3.6f : 2.237f));
    QString ahead_text = QString::number(ahead_kmh);
    int ahead_y = cy + sign_size + 10;
    int ahead_size = sign_size * 2 / 3;

    p.setPen(QPen(QColor(200, 40, 40, 180), 5));
    p.setBrush(QColor(255, 255, 255, 200));
    p.drawEllipse(QPoint(cx, ahead_y), ahead_size / 2, ahead_size / 2);

    p.setPen(QColor(30, 30, 30));
    p.setFont(InterFont(ahead_size / 2, QFont::Bold));
    QFontMetrics afm(p.font());
    QRect ahead_rect = afm.boundingRect(ahead_text);
    ahead_rect.moveCenter(QPoint(cx, ahead_y));
    p.drawText(ahead_rect, Qt::AlignCenter, ahead_text);
  }
}

void HudRendererSP::drawRoadName(QPainter &p, const QRect &surface_rect) {
  // Road name at top center
  int y = surface_rect.top() + 12;

  p.save();
  p.setFont(InterFont(32, QFont::Normal));
  p.setPen(QColor(255, 255, 255, 180));

  QString displayName = roadName;
  QFontMetrics fm(p.font());

  // Truncate if too long
  int max_width = surface_rect.width() - 200;
  if (fm.horizontalAdvance(displayName) > max_width) {
    displayName = fm.elidedText(displayName, Qt::ElideRight, max_width);
  }

  QRect text_rect = fm.boundingRect(displayName);
  text_rect.moveCenter(QPoint(surface_rect.center().x(), y + text_rect.height() / 2));
  p.drawText(text_rect, Qt::AlignCenter, displayName);
  p.restore();
}

void HudRendererSP::drawSteeringArc(QPainter &p, const QRect &surface_rect) {
  // 2026-style steering angle arc at bottom center
  const int arc_width = 400;
  const int arc_height = 80;
  const int margin_bottom = 20;
  const float max_angle = 90.f;  // degrees

  int cx = surface_rect.center().x();
  int cy = surface_rect.bottom() - margin_bottom - arc_height / 2;

  QRect arc_rect(cx - arc_width / 2, cy - arc_height, arc_width, arc_height * 2);

  // Track background arc
  p.save();
  p.setPen(QPen(QColor(255, 255, 255, 50), 8));
  p.setBrush(Qt::NoBrush);
  p.drawArc(arc_rect, 45 * 16, 90 * 16);  // 180 degrees arc

  // Steering angle fill
  float clamped_angle = std::clamp(angleSteers, -max_angle, max_angle);
  if (std::abs(clamped_angle) > 1.f) {
    bool is_active = latActive && !steerOverride;
    QColor arc_color = is_active ? QColor(0, 220, 100, 220) : QColor(180, 180, 180, 180);

    p.setPen(QPen(arc_color, 10));
    int span = (int)(clamped_angle / max_angle * 90 * 16);
    int start = 90 * 16 - span;
    p.drawArc(arc_rect, start, span);
  }

  // Center indicator dot
  p.setPen(Qt::NoPen);
  p.setBrush(QColor(255, 255, 255, 150));
  p.drawEllipse(QPoint(cx, cy), 6, 6);

  p.restore();
}

void HudRendererSP::drawStandstillTimer(QPainter &p, const QRect &surface_rect) {
  // Standstill timer: bottom-right corner, circular badge style
  int min = standstillSeconds / 60;
  int sec = standstillSeconds % 60;
  QString time = (min > 0) ? QString("%1:%2").arg(min).arg(sec, 2, 10, QChar('0'))
                            : QString("%1s").arg(sec);

  const int badge_size = 80;
  int cx = surface_rect.right() - UI_BORDER_SIZE - badge_size;
  int cy = surface_rect.bottom() - UI_BORDER_SIZE - badge_size;

  // Circular background
  p.save();
  p.setPen(Qt::NoPen);
  p.setBrush(QColor(0, 0, 0, 140));
  p.drawEllipse(QPoint(cx, cy), badge_size / 2, badge_size / 2);

  // Timer icon (⏱)
  p.setFont(InterFont(24, QFont::Normal));
  p.setPen(QColor(255, 255, 255, 160));
  QFontMetrics icon_fm(p.font());
  QRect icon_rect = icon_fm.boundingRect("⏱");
  icon_rect.moveCenter(QPoint(cx, cy - 18));
  p.drawText(icon_rect, Qt::AlignCenter, "⏱");

  // Time text
  p.setFont(InterFont(28, QFont::Bold));
  p.setPen(QColor(100, 220, 255, 255));
  QFontMetrics fm(p.font());
  QRect time_rect = fm.boundingRect(time);
  time_rect.moveCenter(QPoint(cx, cy + 15));
  p.drawText(time_rect, Qt::AlignCenter, time);

  p.restore();
}
