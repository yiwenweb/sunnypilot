/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/onroad/hud.h"

#include "selfdrive/ui/qt/util.h"


HudRendererSP::HudRendererSP() : debugPlotsEnabled(false) {}

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
  lkasPrepared = car_state.getLkasPrepared();

  devUiInfo = s.scene.dev_ui_info;

  speedUnit = is_metric ? tr("km/h") : tr("mph");
  lead_d_rel = radar_state.getLeadOne().getDRel();
  lead_v_rel = radar_state.getLeadOne().getVRel();
  lead_status = radar_state.getLeadOne().getStatus();
  steerControlType = car_params.getSteerControlType();
  actuators = car_control.getActuators();
  torqueLateral = steerControlType == cereal::CarParams::SteerControlType::TORQUE;

  angleSteers = car_state.getSteeringAngleDeg();
  // steeringAngleDesiredDeg lives inside the lateralControlState union and only
  // exists for pid/angle/lqr/indi controllers. Torque control (e.g. BYD) has no
  // such field, so read it conditionally and fall back to 0.
  const auto lat_ctrl = cs.getLateralControlState();

  if (lat_ctrl.isPidState()) {
    angleSteersDesired = lat_ctrl.getPidState().getSteeringAngleDesiredDeg();
  } else if (lat_ctrl.isAngleState()) {
    angleSteersDesired = lat_ctrl.getAngleState().getSteeringAngleDesiredDeg();
  } else if (lat_ctrl.isLqrStateDEPRECATED()) {
    angleSteersDesired = lat_ctrl.getLqrStateDEPRECATED().getSteeringAngleDesiredDeg();
  } else if (lat_ctrl.isIndiStateDEPRECATED()) {
    angleSteersDesired = lat_ctrl.getIndiStateDEPRECATED().getSteeringAngleDesiredDeg();
  } else {
    angleSteersDesired = 0.0f;  // torqueState / debugState have no desired angle
  }
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
  debugPlotsEnabled = s.scene.debug_plots;
  laneLineDataEnabled = s.scene.lane_line_data;

  // MICI-style smoothing filters
  {
    float raw_display = -angleSteers;
    float raw_desired = -angleSteersDesired;
    // Faster response for steering arc (alpha 0.25 ≈ 4-frame settling)
    smoothSteerDisplay += (raw_display - smoothSteerDisplay) * 0.25f;
    smoothSteerDesiredDisplay += (raw_desired - smoothSteerDesiredDisplay) * 0.25f;

    // Slower fade for turn signals (alpha 0.12 ≈ 8-frame fade)
    leftBlinkerAlpha += ((leftBlinker ? 1.0f : 0.0f) - leftBlinkerAlpha) * 0.12f;
    rightBlinkerAlpha += ((rightBlinker ? 1.0f : 0.0f) - rightBlinkerAlpha) * 0.12f;
  }

  // Push data to debug plot ring buffers
  if (debugPlotsEnabled) {
    steerHistory.push(angleSteers);
    steerDesHistory.push(angleSteersDesired);
    speedHistory.push(vEgo * (is_metric ? MS_TO_KPH : MS_TO_MPH));
    accelHistory.push(aEgo);
    torqueHistory.push(steeringTorqueEps);
  }

  // Lane line distances (body-center to left/right lane line, c₀ in meters)
  // Guard: modelV2 may be an empty/uninitialized message on the first frames
  // after entering onroad; accessing laneLines[1]/[2] before data arrives
  // triggers a capnp out-of-range → UI SIGABRT → manager reboot loop (stuck logo).
  if (laneLineDataEnabled && sm.rcv_frame("modelV2") > 0) {
    const auto model = sm["modelV2"].getModelV2();
    const auto &lane_lines = model.getLaneLines();
    const auto &lane_line_probs = model.getLaneLineProbs();
    if (lane_lines.size() >= 3 && lane_line_probs.size() >= 3) {
      const auto &left_y = lane_lines[1].getY();
      const auto &right_y = lane_lines[2].getY();
      leftLaneDist  = (lane_line_probs[1] > 0.5f && left_y.size()  > 0) ? left_y[0]  : 0.0f;
      rightLaneDist = (lane_line_probs[2] > 0.5f && right_y.size() > 0) ? right_y[0] : 0.0f;
    } else {
      leftLaneDist = 0.0f;
      rightLaneDist = 0.0f;
    }
  }

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

    // Speed limit block (below MAX set speed, A方案)
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

    // Lane line distance box (top-left)
    if (laneLineDataEnabled) {
      drawLaneLineData(p, surface_rect);
    }

    // Debug plots overlay (left side, semi-transparent)
    if (debugPlotsEnabled) {
      drawDebugPlots(p, surface_rect);
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
  y += 55;
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

  return 108;
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

  // Order reversed vs. original to spread static positions (anti burn-in).
  // Sizes unchanged; only the sequence of items is swapped.
  UiElement altitudeElement = DeveloperUi::getAltitude(gpsAccuracy, altitude);
  rw += drawBottomDevUIElement(p, rw, y, altitudeElement.value, altitudeElement.label, altitudeElement.units, altitudeElement.color);

  if (torqueLateral && torquedUseParams) {
    UiElement latAccelFactorFilteredElement = DeveloperUi::getLatAccelFactorFiltered(latAccelFactorFiltered, liveValid);
    rw += drawBottomDevUIElement(p, rw, y, latAccelFactorFilteredElement.value, latAccelFactorFilteredElement.label, latAccelFactorFilteredElement.units, latAccelFactorFilteredElement.color);

    UiElement frictionCoefficientFilteredElement = DeveloperUi::getFrictionCoefficientFiltered(frictionCoefficientFiltered, liveValid);
    rw += drawBottomDevUIElement(p, rw, y, frictionCoefficientFilteredElement.value, frictionCoefficientFilteredElement.label, frictionCoefficientFilteredElement.units, frictionCoefficientFilteredElement.color);
  } else {
    UiElement bearingDegElement = DeveloperUi::getBearingDeg(bearingAccuracyDeg, bearingDeg);
    rw += drawBottomDevUIElement(p, rw, y, bearingDegElement.value, bearingDegElement.label, bearingDegElement.units, bearingDegElement.color);

    UiElement steeringTorqueEpsElement = DeveloperUi::getSteeringTorqueEps(steeringTorqueEps);
    rw += drawBottomDevUIElement(p, rw, y, steeringTorqueEpsElement.value, steeringTorqueEpsElement.label, steeringTorqueEpsElement.units, steeringTorqueEpsElement.color);
  }

  UiElement vEgoLeadElement = DeveloperUi::getVEgoLead(lead_status, lead_v_rel, vEgo, is_metric, speedUnit);
  rw += drawBottomDevUIElement(p, rw, y, vEgoLeadElement.value, vEgoLeadElement.label, vEgoLeadElement.units, vEgoLeadElement.color);

  UiElement aEgoElement = DeveloperUi::getAEgo(aEgo);
  rw += drawBottomDevUIElement(p, rw, y, aEgoElement.value, aEgoElement.label, aEgoElement.units, aEgoElement.color);

  UiElement lkasPreparedElement = DeveloperUi::getLkasPrepared(lkasPrepared);
  rw += drawBottomDevUIElement(p, rw, y, lkasPreparedElement.value, lkasPreparedElement.label, lkasPreparedElement.units, lkasPreparedElement.color);
}

void HudRendererSP::drawAccelBar(QPainter &p, const QRect &surface_rect) {
  // RocketFuel: vertical bar on the left side (ported from sunnypilot 2026)
  // MICI-style: gradient color + smooth animation
  const int bar_width = 36;
  const int bar_height = surface_rect.height();  // 拉满全屏高度
  const float max_accel = 3.0f;
  // Tucked to the far left so it never overlaps the set-speed / data boxes
  // (metric set-speed box left edge = 46, imperial = 60; bar right edge = 42)
  const int margin_left = 6;

  int track_x = margin_left;
  int track_y = 0;

  // Background track
  p.setPen(Qt::NoPen);
  p.setBrush(QColor(0, 0, 0, 100));
  p.drawRoundedRect(track_x, track_y, bar_width, bar_height, bar_width / 2, bar_width / 2);

  // Center zero line
  int center_y = track_y + bar_height / 2;
  p.setPen(QPen(QColor(255, 255, 255, 70), 1));
  p.drawLine(track_x + 4, center_y, track_x + bar_width - 4, center_y);

  // Filled portion with MICI-style gradient
  float accel_val = std::clamp(smoothAEgo, -max_accel, max_accel);
  int fill_height = (int)(std::abs(accel_val) / max_accel * (bar_height / 2 - 4));

  if (fill_height > 1) {
    float abs_ratio = std::abs(accel_val) / max_accel;
    QColor color;
    int fill_y;

    if (accel_val >= 0) {
      // Accel: MICI gradient white → green → yellow at high accel
      float yellow_t = std::clamp((abs_ratio - 0.75f) * 4.0f, 0.0f, 1.0f);
      int r = (int)(255.0f * (1.0f - yellow_t * 0.2f));
      int g = (int)(140.0f + 115.0f * (1.0f - yellow_t * 0.7f));
      int b = (int)(80.0f * (1.0f - yellow_t));
      color = QColor(r, g, b, 200);
      fill_y = center_y - fill_height;
    } else {
      // Decel: MICI gradient red → orange
      float orange_t = std::clamp((abs_ratio - 0.75f) * 4.0f, 0.0f, 1.0f);
      int r = 220 + (int)(35.0f * orange_t);
      int g = (int)(55.0f * (1.0f - orange_t * 0.8f));
      int b = (int)(55.0f * (1.0f - orange_t));
      color = QColor(r, g, b, 200);
      fill_y = center_y;
    }

    p.setPen(Qt::NoPen);
    p.setBrush(color);
    p.drawRoundedRect(track_x + 4, fill_y, bar_width - 8, fill_height, 6, 6);
  }
}

void HudRendererSP::drawTurnSignals(QPainter &p, const QRect &surface_rect) {
  // MICI-style turn signal indicators with smooth fade and rotation pop-in
  const int arrow_size = 55;
  const int margin = 40;
  int cy = surface_rect.center().y();

  auto drawArrow = [&](int cx, int pointingLeft, float alpha) {
    if (alpha < 0.01f) return;

    int dir = pointingLeft ? -1 : 1;

    p.save();
    p.setPen(Qt::NoPen);

    // Glow background (fades with alpha)
    p.setBrush(QColor(0, 220, 80, (int)(60 * alpha)));
    p.drawEllipse(QPoint(cx, cy), arrow_size, arrow_size * 2 / 3);

    // MICI-style: slight rotation pop-in (0 → 30° fade in)
    float rotation_offset = (1.0f - alpha) * 30.0f * dir;

    p.translate(cx, cy);
    p.rotate(rotation_offset);

    // Arrow body
    QPainterPath arrow;

    // Triangle points (relative to origin)
    QPointF tip(dir * arrow_size * 0.7, 0);
    QPointF base1(-dir * arrow_size * 0.3, -arrow_size * 0.5);
    QPointF base2(-dir * arrow_size * 0.3, arrow_size * 0.5);

    arrow.moveTo(tip);
    arrow.lineTo(base1);
    arrow.lineTo(base2);
    arrow.closeSubpath();

    QRectF stem(-dir * arrow_size * 0.6, -arrow_size * 0.15,
                arrow_size * 0.6, arrow_size * 0.3);

    p.setBrush(QColor(0, 255, 90, (int)(220 * alpha)));
    p.drawPath(arrow);
    p.drawRoundedRect(stem, 3, 3);

    p.restore();
  };

  drawArrow(margin + arrow_size / 2, true, leftBlinkerAlpha);
  drawArrow(surface_rect.right() - margin - arrow_size / 2, false, rightBlinkerAlpha);
}

void HudRendererSP::drawSpeedLimit(QPainter &p, const QRect &surface_rect) {
  // 横向布局：ACC设定速度（左）+ 限速标志（右），同宽同高
  const QSize default_size = {172, 204};
  QSize box_size = is_metric ? QSize(200, 204) : default_size;
  const int block_h = 204;
  const int sign_area_w = 120;        // 限速标志区域宽度
  const int block_w = box_size.width() + sign_area_w;  // ACC宽 + 限速区宽
  const int box_x = 60 + (default_size.width() - box_size.width()) / 2;
  const int box_y = 45;

  int limit_kmh = (int)(speedLimit * (is_metric ? 3.6f : 2.237f));
  QString limit_text = QString::number(limit_kmh);
  QString setSpeedStr = is_cruise_set ? QString::number(std::nearbyint(set_speed)) : QString::fromUtf8("–");

  p.save();

  // === 统一方框背景 ===
  p.setPen(QPen(QColor(255, 255, 255, 75), 6));
  p.setBrush(QColor(0, 0, 0, 166));
  p.drawRoundedRect(box_x, box_y, block_w, block_h, 32, 32);

  // === ACC设定速度区域（左侧，与原生 drawSetSpeed 完全一致） ===
  QColor max_color = QColor(0xa6, 0xa6, 0xa6, 0xff);
  QColor set_speed_color = QColor(0x72, 0x72, 0x72, 0xff);
  if (is_cruise_set) {
    set_speed_color = QColor(255, 255, 255);
    if (status == STATUS_DISENGAGED) {
      max_color = QColor(255, 255, 255);
    } else if (status == STATUS_OVERRIDE) {
      max_color = QColor(0x91, 0x9b, 0x95, 0xff);
    } else {
      max_color = QColor(0x80, 0xd8, 0xa6, 0xff);
    }
  }

  // "MAX" 标签
  p.setFont(InterFont(40, QFont::DemiBold));
  p.setPen(max_color);
  QRect max_rect(box_x, box_y + 27, box_size.width(), 40);
  p.drawText(max_rect, Qt::AlignTop | Qt::AlignHCenter, tr("MAX"));

  // 设定速度数字
  p.setFont(InterFont(90, QFont::Bold));
  p.setPen(set_speed_color);
  QRect speed_rect(box_x, box_y + 77, box_size.width(), 90);
  p.drawText(speed_rect, Qt::AlignTop | Qt::AlignHCenter, setSpeedStr);

  // === 竖分隔线 ===
  int div_x = box_x + box_size.width() + 10;
  p.setPen(QPen(QColor(255, 255, 255, 50), 1));
  p.drawLine(div_x, box_y + 28, div_x, box_y + block_h - 28);

  // === 限速标志区域（右侧，垂直居中） ===
  // Tesla 风格：白底圆角矩形
  const int sign_w = 96;
  const int sign_h = 66;
  const int sign_radius = 12;
  int sign_area_cx = box_x + box_size.width() + sign_area_w / 2;
  int sign_x = sign_area_cx - sign_w / 2;
  int sign_y = box_y + (block_h - sign_h) / 2;

  p.setPen(QPen(QColor(80, 80, 80, 180), 3));
  p.setBrush(QColor(255, 255, 255, 245));
  p.drawRoundedRect(sign_x, sign_y, sign_w, sign_h, sign_radius, sign_radius);

  // 限速数字
  p.setPen(QColor(30, 30, 30));
  p.setFont(InterFont(44, QFont::Bold));
  QRect sign_text_rect(sign_x, sign_y, sign_w, sign_h);
  p.drawText(sign_text_rect, Qt::AlignCenter, limit_text);

  // 限速标签（紧贴标志下方）
  QString label_text;
  if (speedLimitAheadValid) {
    int ahead_kmh = (int)(speedLimitAhead * (is_metric ? 3.6f : 2.237f));
    label_text = QString("LIMIT  → %1").arg(ahead_kmh);
  } else {
    label_text = "LIMIT";
  }

  p.setPen(QColor(180, 180, 180, 200));
  p.setFont(InterFont(20, QFont::Medium));
  QFontMetrics lfm(p.font());
  QRect label_rect = lfm.boundingRect(label_text);
  int label_y = sign_y + sign_h + 12;
  label_rect.moveCenter(QPoint(sign_area_cx, label_y + label_rect.height() / 2));
  p.drawText(label_rect, Qt::AlignCenter, label_text);

  p.restore();
}

void HudRendererSP::drawRoadName(QPainter &p, const QRect &surface_rect) {
  // Road name at top center
  int y = surface_rect.top() + 24;

  p.save();
  p.setFont(InterFont(56, QFont::Normal));
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
  // MICI-style steering arc: gradient color (white→yellow→orange) + smooth filter + dynamic sizing
  // Tuned: arc_height -10%, arc_width +20%(+5% from 1087), line thickness -5%, center dot hidden
  const int arc_width = 1087;       // +20% (原900), 再+5%
  const int arc_height = 210;       // -10% (原234)，弧度更扁平
  const int margin_bottom = -102;  // 弧两端距底部信息栏50px
  const float max_angle = 55.f;
  const int half_span = 54;         // 弧半跨度（°）

  int cx = surface_rect.center().x();
  int cy = surface_rect.bottom() - margin_bottom - arc_height / 2;

  QRect arc_rect(cx - arc_width / 2, cy - arc_height, arc_width, arc_height * 2);

  float clamped_angle = std::clamp(smoothSteerDisplay, -max_angle, max_angle);
  float clamped_desired = std::clamp(smoothSteerDesiredDisplay, -max_angle, max_angle);

  bool is_active = latActive && !steerOverride;

  p.save();
  p.setRenderHint(QPainter::Antialiasing);

  // Background arc（厚度-5%：36→34）
  p.setPen(QPen(QColor(255, 255, 255, 45), 34));
  p.setBrush(Qt::NoBrush);
  p.drawArc(arc_rect, (90 - half_span) * 16, (half_span * 2) * 16);

  // Tick marks removed

  // MICI-style gradient fill: white at center → yellow at 75% → orange at 100%
  {
    float abs_ratio = std::abs(clamped_angle) / max_angle;
    float yellow_t = std::clamp((abs_ratio - 0.75f) * 4.0f, 0.0f, 1.0f);

    QColor fill_color;
    if (is_active) {
      int g = (int)(255.0f * (1.0f - yellow_t * 0.55f));
      int b = (int)(255.0f * (1.0f - yellow_t));
      fill_color = QColor(255, g, b, 255);
    } else {
      fill_color = QColor(180, 180, 180, 240);
    }

    if (std::abs(clamped_angle) > 1.f) {
      // Dynamic line width（厚度-5%：39→37，21→20）
      float pen_width = 37.0f + abs_ratio * 20.0f;
      p.setPen(QPen(fill_color, pen_width, Qt::SolidLine, Qt::RoundCap));
      int span = (int)(clamped_angle / max_angle * half_span * 16);
      p.drawArc(arc_rect, 90 * 16, span);
    }
  }

  // Desired angle indicator (diamond marker)
  if (std::abs(clamped_desired) > 1.f) {
    double target_rad = (90.0 - clamped_desired / max_angle * half_span) * M_PI / 180.0;
    int mx = cx + (int)((arc_width / 2 - 6) * cos(target_rad));
    int my = cy - (int)((arc_height - 6) * sin(target_rad));

    QPolygon diamond;
    diamond << QPoint(mx, my - 14)
            << QPoint(mx + 11, my)
            << QPoint(mx, my + 14)
            << QPoint(mx - 11, my);
    p.setPen(Qt::NoPen);
    p.setBrush(is_active ? QColor(255, 255, 255, 255) : QColor(200, 200, 200, 216));
    p.drawPolygon(diamond);
  }

  // Center dot removed

  p.restore();
}

void HudRendererSP::drawDebugPlots(QPainter &p, const QRect &surface_rect) {
  // 4-panel debug plot overlay (top-left, enlarged 4x area)
  constexpr int PANEL_W = 840;   // 2x width
  constexpr int PANEL_H = 200;   // 2x height
  constexpr int MARGIN = 20;
  constexpr int LABEL_W = 95;
  constexpr int N = DebugPlotHistory::SIZE;

  int panel_x = surface_rect.left() + MARGIN;
  int panel_y = surface_rect.top() + MARGIN + 20;

  // Helper: draw a single panel with one or two lines
  auto drawPanel = [&](int y, const QString& title, const QString& unit,
                       double y_min, double y_max,
                       const DebugPlotHistory& h0, QColor c0,
                       const DebugPlotHistory* h1 = nullptr, QColor c1 = {}) {
    // Panel background
    p.setPen(Qt::NoPen);
    p.setBrush(QColor(0, 0, 0, 150));
    p.drawRoundedRect(panel_x, y, PANEL_W, PANEL_H, 10, 10);

    // Title (top-left, larger)
    p.setFont(InterFont(28, QFont::Normal));
    p.setPen(QColor(200, 200, 200, 180));
    p.drawText(QRect(panel_x + 10, y + 4, PANEL_W - 20, 28), Qt::AlignLeft | Qt::AlignVCenter, title);

    // Y-axis labels
    p.setFont(InterFont(24, QFont::Normal));
    p.setPen(QColor(180, 180, 180, 150));
    p.drawText(QRect(panel_x + 4, y + 32, LABEL_W, 26), Qt::AlignRight, QString::number(y_max, 'f', 1));
    p.drawText(QRect(panel_x + 4, y + PANEL_H - 32, LABEL_W, 26), Qt::AlignRight, QString::number(y_min, 'f', 1));

    // Unit
    p.setFont(InterFont(20, QFont::Normal));
    p.setPen(QColor(160, 160, 160, 140));
    p.drawText(QRect(panel_x + 4, y + PANEL_H / 2 - 12, LABEL_W, 24), Qt::AlignRight, unit);

    // Plot area
    int plot_x = panel_x + LABEL_W + 8;
    int plot_w = PANEL_W - LABEL_W - 16;
    int plot_y = y + 32;
    int plot_h = PANEL_H - 40;

    // Clipping
    p.save();
    p.setClipRect(plot_x, plot_y, plot_w, plot_h);

    // Zero line
    double zero_norm = -y_min / (y_max - y_min);
    int zero_y = plot_y + plot_h - (int)(zero_norm * plot_h);
    if (y_min < 0 && y_max > 0) {
      p.setPen(QPen(QColor(255, 255, 255, 60), 2, Qt::DashLine));
      p.drawLine(plot_x, zero_y, plot_x + plot_w, zero_y);
    }

    // Convert ring buffer to points and draw
    auto drawLine = [&](const DebugPlotHistory& hist, QColor color, float line_w) {
      QVector<QPointF> pts;
      pts.reserve(N);
      for (int i = 0; i < N; i++) {
        float val = std::clamp(hist.get(i), (float)y_min, (float)y_max);
        float norm = (val - (float)y_min) / (float)(y_max - y_min);
        float px = plot_x + (float)i / (N - 1) * plot_w;
        float py = plot_y + plot_h - norm * plot_h;
        pts.append(QPointF(px, py));
      }
      p.setPen(QPen(color, line_w));
      p.setBrush(Qt::NoBrush);
      p.drawPolyline(pts.data(), pts.size());
    };

    drawLine(h0, c0, 3.5f);
    if (h1) drawLine(*h1, c1, 2.5f);

    p.restore();
  };

  int cur_y = panel_y;

  // Panel 1: 转向角 Steering Angle
  drawPanel(cur_y, "转向角", "°", -100.f, 100.f,
            steerHistory, QColor(80, 160, 255),
            &steerDesHistory, QColor(80, 255, 140));
  cur_y += PANEL_H + 12;

  // Panel 2: 速度 Speed
  drawPanel(cur_y, "速度", "km/h", 0.f, 160.f,
            speedHistory, QColor(80, 160, 255));
  cur_y += PANEL_H + 12;

  // Panel 3: 加速度 Acceleration
  drawPanel(cur_y, "加速度", "m/s²", -3.f, 3.f,
            accelHistory, QColor(80, 160, 255));
  cur_y += PANEL_H + 12;

  // Panel 4: EPS扭矩
  drawPanel(cur_y, "EPS扭矩", "", -3000.f, 3000.f,
            torqueHistory, QColor(255, 180, 60));
}


void HudRendererSP::drawStandstillTimer(QPainter &p, const QRect &surface_rect) {
  // Standstill timer: middle-right of screen, large circular badge
  int min = standstillSeconds / 60;
  int sec = standstillSeconds % 60;
  QString time = (min > 0) ? QString("%1:%2").arg(min).arg(sec, 2, 10, QChar('0'))
                            : QString("%1s").arg(sec);

  const int badge_size = 570;
  int cx = surface_rect.center().x() + surface_rect.width() / 4;
  int cy = surface_rect.center().y();

  // Circular background
  p.save();
  p.setPen(Qt::NoPen);
  p.setBrush(QColor(0, 0, 0, 160));
  p.drawEllipse(QPoint(cx, cy), badge_size / 2, badge_size / 2);

  // Timer icon (⏱)
  p.setFont(InterFont(152, QFont::Normal));
  p.setPen(QColor(255, 255, 255, 180));
  QFontMetrics icon_fm(p.font());
  QRect icon_rect = icon_fm.boundingRect("⏱");
  icon_rect.moveCenter(QPoint(cx, cy - 120));
  p.drawText(icon_rect, Qt::AlignCenter, "⏱");

  // Time text
  p.setFont(InterFont(176, QFont::Bold));
  p.setPen(QColor(100, 220, 255, 255));
  QFontMetrics fm(p.font());
  QRect time_rect = fm.boundingRect(time);
  time_rect.moveCenter(QPoint(cx, cy + 110));
  p.drawText(time_rect, Qt::AlignCenter, time);

  p.restore();
}

void HudRendererSP::drawLaneLineData(QPainter &p, const QRect &surface_rect) {
  // Lane line distance box, SAME size & alignment as the MAX set-speed box
  const QSize default_size = {172, 204};
  QSize box_size = is_metric ? QSize(200, 204) : default_size;
  const int box_x = 60 + (default_size.width() - box_size.width()) / 2;
  const int box_y = 400;  // 紧贴在限速一体化方框下方 (375 + 25 gap)

  // Draw box
  p.setPen(QPen(QColor(255, 255, 255, 75), 6));
  p.setBrush(QColor(0, 0, 0, 166));
  p.drawRoundedRect(box_x, box_y, box_size.width(), box_size.height(), 32, 32);

  int cx = box_x + box_size.width() / 2;
  const int gap = 10;

  // Line 1: 左边 <value>m
  QString left_lbl = tr("左边");
  p.setFont(InterFont(30, QFont::Normal));
  int lbl_w = p.fontMetrics().horizontalAdvance(left_lbl);
  QString left_str = (leftLaneDist != 0.0f) ? QString::number(std::fabs(leftLaneDist), 'f', 2) + "m" : "-";
  p.setFont(InterFont(42, QFont::Bold));
  int val_w = p.fontMetrics().horizontalAdvance(left_str);
  int total_w = lbl_w + gap + val_w;
  int start_x = cx - total_w / 2;
  int line1_y = box_y + 72;
  p.setFont(InterFont(30, QFont::Normal));
  p.setPen(QColor(160, 200, 255, 230));
  p.drawText(start_x, line1_y, left_lbl);
  p.setFont(InterFont(42, QFont::Bold));
  p.setPen(Qt::white);
  p.drawText(start_x + lbl_w + gap, line1_y, left_str);

  // Line 2: 右边 <value>m
  QString right_lbl = tr("右边");
  p.setFont(InterFont(30, QFont::Normal));
  int lbl2_w = p.fontMetrics().horizontalAdvance(right_lbl);
  QString right_str = (rightLaneDist != 0.0f) ? QString::number(std::fabs(rightLaneDist), 'f', 2) + "m" : "-";
  p.setFont(InterFont(42, QFont::Bold));
  int val2_w = p.fontMetrics().horizontalAdvance(right_str);
  int total2_w = lbl2_w + gap + val2_w;
  int start2_x = cx - total2_w / 2;
  int line2_y = box_y + 152;
  p.setFont(InterFont(30, QFont::Normal));
  p.setPen(QColor(160, 255, 180, 230));
  p.drawText(start2_x, line2_y, right_lbl);
  p.setFont(InterFont(42, QFont::Bold));
  p.setPen(Qt::white);
  p.drawText(start2_x + lbl2_w + gap, line2_y, right_str);
}
