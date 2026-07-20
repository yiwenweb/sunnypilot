/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/onroad/model.h"

#include "selfdrive/ui/sunnypilot/qt/onroad/ui_colors.h"

ModelRendererSP::ModelRendererSP() {
  initRainbowLUT();
}

void ModelRendererSP::initRainbowLUT() {
  for (int i = 0; i < RAINBOW_LUT_SIZE; i++) {
    float hue = i * 360.0f / RAINBOW_LUT_SIZE;
    rainbowLUT[i] = QColor::fromHslF(hue / 360.0f, 0.9f, 0.6f);
  }
  rainbowLUTInitialized = true;
}

void ModelRendererSP::update_model(const cereal::ModelDataV2::Reader &model, const cereal::RadarState::LeadData::Reader &lead) {
  ModelRenderer::update_model(model, lead);
  const auto &model_position = model.getPosition();
  const auto &lane_lines = model.getLaneLines();
  float max_distance = std::clamp(*(model_position.getX().end() - 1), MIN_DRAW_DISTANCE, MAX_DRAW_DISTANCE);
  int max_idx = get_path_length_idx(lane_lines[0], max_distance);
  // update blindspot vertices
  float max_distance_barrier = 100;
  int max_idx_barrier = std::min(max_idx, get_path_length_idx(lane_lines[0], max_distance_barrier));
  mapLineToPolygon(model.getLaneLines()[1], 0.2, -0.05, &left_blindspot_vertices, max_idx_barrier);
  mapLineToPolygon(model.getLaneLines()[2], 0.2, -0.05, &right_blindspot_vertices, max_idx_barrier);
}

void ModelRendererSP::drawPath(QPainter &painter, const cereal::ModelDataV2::Reader &model, const QRect &surface_rect) {
  auto *s = uiState();
  auto &sm = *(s->sm);
  bool blindspot = Params().getBool("BlindSpot");

  // P3: 盲点渐变缓存（几何变化时重建）
  if (surface_rect != lastSurfaceRect) {
    blindspotGradientDirty = true;
    lastSurfaceRect = surface_rect;
  }

  if (blindspot) {
    bool left_blindspot = sm["carState"].getCarState().getLeftBlindspot();
    bool right_blindspot = sm["carState"].getCarState().getRightBlindspot();

    if (blindspotGradientDirty) {
      // 左盲点渐变：左橙右黄
      leftBlindspotGradient = QLinearGradient(0, 0, surface_rect.width(), 0);
      leftBlindspotGradient.setColorAt(0.0, SPColor::withAlpha(SPColor::Warning, 102));
      leftBlindspotGradient.setColorAt(1.0, SPColor::withAlpha(SPColor::AccelYellow, 102));

      // 右盲点渐变：右橙左黄
      rightBlindspotGradient = QLinearGradient(surface_rect.width(), 0, 0, 0);
      rightBlindspotGradient.setColorAt(0.0, SPColor::withAlpha(SPColor::Warning, 102));
      rightBlindspotGradient.setColorAt(1.0, SPColor::withAlpha(SPColor::AccelYellow, 102));

      blindspotGradientDirty = false;
    }

    if (left_blindspot && !left_blindspot_vertices.isEmpty()) {
      painter.setBrush(leftBlindspotGradient);
      painter.drawPolygon(left_blindspot_vertices);
    }

    if (right_blindspot && !right_blindspot_vertices.isEmpty()) {
      painter.setBrush(rightBlindspotGradient);
      painter.drawPolygon(right_blindspot_vertices);
    }
  }

  bool rainbow = Params().getBool("RainbowMode");

  if (rainbow) {
    // P3: 彩虹路径 LUT 优化（预渲染 256 色，消除每帧 HSL 计算）
    float time_offset = std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count() / 1000.0f;

    float animation_speed = 40.0f;
    int hue_offset = (int)(time_offset * animation_speed) % RAINBOW_LUT_SIZE;

    QLinearGradient bg(0, surface_rect.height(), 0, 0);

    const int num_stops = 7;
    for (int i = 0; i < num_stops; i++) {
      float position = static_cast<float>(i) / (num_stops - 1);

      // 从 LUT 取样（消除 fromHslF 计算）
      int lut_idx = (hue_offset + (int)(position * RAINBOW_LUT_SIZE)) % RAINBOW_LUT_SIZE;
      QColor color = rainbowLUT[lut_idx];

      // Alpha fades out towards the far end
      float alpha = 0.8f * (1.0f - position * 0.3f);
      color.setAlphaF(alpha);

      bg.setColorAt(position, color);
    }

    painter.setBrush(bg);
    painter.drawPolygon(track_vertices);
  } else {
    // Normal path rendering
    ModelRenderer::drawPath(painter, model, surface_rect.height());
  }
}
