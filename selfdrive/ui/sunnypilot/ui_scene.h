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
  int speed_limit_style = 1;  // 0=rect, 1=circle, 2=large_circle
  bool speed_limit_color_max = true;
  bool speed_limit_show_source = false;
  int speed_limit_warn_threshold = 10;
  int speed_limit_danger_threshold = 20;
  bool road_name = false;
  bool steering_arc = false;
  bool standstill_timer = false;
  bool debug_plots = false;
  bool lane_line_data = false;
  bool scc_vision_enabled = false;
  bool scc_map_enabled = false;
} UISceneSP;
