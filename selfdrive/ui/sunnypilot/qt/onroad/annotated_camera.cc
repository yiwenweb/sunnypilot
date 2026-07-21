/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/onroad/annotated_camera.h"

#include <QPainterPath>

AnnotatedCameraWidgetSP::AnnotatedCameraWidgetSP(VisionStreamType type, QWidget *parent)
    : AnnotatedCameraWidget(type, parent) {
}

void AnnotatedCameraWidgetSP::updateState(const UIState &s) {
  AnnotatedCameraWidget::updateState(s);
}

void AnnotatedCameraWidgetSP::paintGL() {
  // 先绘制摄像头画面（OpenGL 帧）
  CameraWidget::paintGL();

  // 用 QPainter 绘制圆角遮罩 + 所有 HUD 叠加
  QPainter painter(this);
  painter.setRenderHint(QPainter::Antialiasing);

  // 圆角裁剪路径（整个摄像头画面区域）
  const int corner_radius = 32;
  QPainterPath clip_path;
  clip_path.addRoundedRect(rect(), corner_radius, corner_radius);
  painter.setClipPath(clip_path);

  // 在圆角裁剪区域内绘制模型、驾驶员监控、HUD
  UIState *s = uiState();
  model.draw(painter, rect());
  dmon.draw(painter, rect());
  hud.updateState(*s);
  hud.draw(painter, rect());

  // 取消裁剪，绘制圆角边框
  painter.setClipping(false);
  painter.setPen(QPen(QColor(255, 255, 255, 30), 1));
  painter.setBrush(Qt::NoBrush);
  painter.drawRoundedRect(rect(), corner_radius, corner_radius);
}

void AnnotatedCameraWidgetSP::showEvent(QShowEvent *event) {
  AnnotatedCameraWidget::showEvent(event);
  ui_update_params_sp(uiState());
}
