/**
  * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
  *
  * This file is part of sunnypilot and is licensed under the MIT License.
  * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

typedef struct UISceneSP : UIScene {
  int dev_ui_info = 0;
  bool accel_bar = false;
  bool turn_signal = false;
  bool speed_limit = false;
  bool road_name = false;
  bool steering_arc = false;
  bool standstill_timer = false;
  bool debug_plots = false;
  bool lane_line_data = false;
} UISceneSP;
