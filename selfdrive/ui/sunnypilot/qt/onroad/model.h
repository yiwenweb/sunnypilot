/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

#include <array>
#include <QPixmap>
#include "selfdrive/ui/qt/onroad/model.h"

class ModelRendererSP : public ModelRenderer {
public:
  ModelRendererSP();

private:
  void update_model(const cereal::ModelDataV2::Reader &model, const cereal::RadarState::LeadData::Reader &lead) override;
  void drawPath(QPainter &painter, const cereal::ModelDataV2::Reader &model, const QRect &rect) override;

  QPolygonF left_blindspot_vertices;
  QPolygonF right_blindspot_vertices;

  // P3: 彩虹路径 LUT（预渲染 256 色，消除每帧 HSL 计算）
  static constexpr int RAINBOW_LUT_SIZE = 256;
  std::array<QColor, RAINBOW_LUT_SIZE> rainbowLUT;
  bool rainbowLUTInitialized = false;
  void initRainbowLUT();

  // P3: 盲点渐变缓存（几何不变时复用）
  QLinearGradient leftBlindspotGradient;
  QLinearGradient rightBlindspotGradient;
  QRect lastSurfaceRect;
  bool blindspotGradientDirty = true;
};
