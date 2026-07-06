/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#pragma once

#include <QThread>
#include <QTimer>
#include "selfdrive/ui/qt/window.h"
#include "selfdrive/ui/sunnypilot/qt/home.h"
#include "selfdrive/ui/sunnypilot/qt/offroad/settings/settings.h"

class ScreenStreamer;

class MainWindowSP : public MainWindow {
  Q_OBJECT

public:
  explicit MainWindowSP(QWidget *parent = 0);
  ~MainWindowSP() override;

private:
  HomeWindowSP *homeWindow;
  SettingsWindowSP *settingsWindow;
  void closeSettings() override;

  // 屏幕实时流服务（供 Android 视频预览使用）
  QThread *streamer_thread = nullptr;
  ScreenStreamer *streamer = nullptr;
  QTimer *capture_timer = nullptr;
  void captureAndSendFrame();
};
