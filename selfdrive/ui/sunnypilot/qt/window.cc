/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/window.h"

#include <QBuffer>
#include <QPixmap>
#include "common/params.h"
#include "selfdrive/ui/qt/screenstreamer.h"

MainWindowSP::MainWindowSP(QWidget *parent)
    : MainWindow(parent, new HomeWindowSP(parent), new SettingsWindowSP(parent)) {

  homeWindow = dynamic_cast<HomeWindowSP *>(MainWindow::homeWindow);
  settingsWindow = dynamic_cast<SettingsWindowSP *>(MainWindow::settingsWindow);

  // 初始化屏幕实时流服务（独立线程，端口 8083）
  streamer = new ScreenStreamer();
  streamer_thread = new QThread(this);
  streamer->moveToThread(streamer_thread);
  QObject::connect(streamer_thread, &QThread::started, streamer, [this]() {
    streamer->start(8083);
  });
  QObject::connect(streamer_thread, &QThread::finished, streamer, &QObject::deleteLater);
  streamer_thread->start();

  // 定时截屏，每 150ms（约 6.7Hz）抓取一次顶层窗口
  capture_timer = new QTimer(this);
  QObject::connect(capture_timer, &QTimer::timeout, this, &MainWindowSP::captureAndSendFrame);
  capture_timer->start(150);
}

MainWindowSP::~MainWindowSP() {
  if (capture_timer) {
    capture_timer->stop();
  }
  if (streamer) {
    QMetaObject::invokeMethod(streamer, "stop", Qt::QueuedConnection);
  }
  if (streamer_thread) {
    streamer_thread->quit();
    streamer_thread->wait(3000);
  }
}

void MainWindowSP::closeSettings() {
  MainWindow::closeSettings();
}

void MainWindowSP::captureAndSendFrame() {
  if (!streamer || !isVisible()) return;

  // 同步 ScreenStreamEnabled 参数到 streamer 开关状态
  bool paramEnabled = Params().getBool("ScreenStreamEnabled");
  if (paramEnabled != streamer->isEnabled()) {
    QMetaObject::invokeMethod(streamer, "setEnabled",
                              Qt::QueuedConnection, Q_ARG(bool, paramEnabled));
  }

  if (!streamer->isEnabled()) return;

  QPixmap screenshot = grab();
  if (screenshot.isNull()) return;

  // 缩放到 50%（C3 屏幕 1920x1080 → 960x540）
  QPixmap scaled = screenshot.scaled(screenshot.width() / 2, screenshot.height() / 2,
                                     Qt::KeepAspectRatio, Qt::FastTransformation);

  QByteArray jpeg;
  QBuffer buffer(&jpeg);
  buffer.open(QIODevice::WriteOnly);
  scaled.save(&buffer, "JPEG", 70);

  QMetaObject::invokeMethod(streamer, "setLatestFrame",
                            Qt::QueuedConnection, Q_ARG(QByteArray, jpeg));
}
