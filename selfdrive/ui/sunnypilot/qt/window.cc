/**
 * Copyright (c) 2021-, Haibin Wen, sunnypilot, and a number of other contributors.
 *
 * This file is part of sunnypilot and is licensed under the MIT License.
 * See the LICENSE.md file in the root directory for more details.
 */

#include "selfdrive/ui/sunnypilot/qt/window.h"

#include <QBuffer>
#include <QDateTime>
#include <QGuiApplication>
#include <QScreen>
#include <QPixmap>
#include "common/params.h"
#include "selfdrive/ui/qt/screenstreamer.h"

// 性能优化参数
static const int CAPTURE_INTERVAL_MS = 300;   // 3.3 fps（预览够用）
static const int CAPTURE_WIDTH = 960;          // 目标宽度（C3 1920 / 2，手机端清晰）
static const int CAPTURE_HEIGHT = 540;         // 目标高度（C3 1080 / 2）
static const int JPEG_QUALITY = 70;            // JPEG 质量（70=清晰+合理大小）
static const int IDLE_TIMEOUT_MS = 3000;       // 空闲超时：3秒无客户端则暂停

MainWindowSP::MainWindowSP(QWidget *parent)
    : MainWindow(parent, new HomeWindowSP(parent), new SettingsWindowSP(parent)) {

  homeWindow = dynamic_cast<HomeWindowSP *>(MainWindow::homeWindow);
  settingsWindow = dynamic_cast<SettingsWindowSP *>(MainWindow::settingsWindow);

  // 初始化屏幕实时流服务（独立线程，端口 8083）
  streamer = new ScreenStreamer();
  streamer->setTargetWidget(this);
  streamer_thread = new QThread(this);
  streamer->moveToThread(streamer_thread);
  QObject::connect(streamer_thread, &QThread::started, streamer, [this]() {
    streamer->start(8083);
  });
  QObject::connect(streamer_thread, &QThread::finished, streamer, &QObject::deleteLater);
  streamer_thread->start();

  // 定时截屏（300ms间隔 + 空闲自动暂停）
  capture_timer = new QTimer(this);
  QObject::connect(capture_timer, &QTimer::timeout, this, &MainWindowSP::captureAndSendFrame);
  capture_timer->start(CAPTURE_INTERVAL_MS);
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

  // 同步 ScreenStreamEnabled 参数
  bool paramEnabled = Params().getBool("ScreenStreamEnabled");
  if (paramEnabled != streamer->isEnabled()) {
    QMetaObject::invokeMethod(streamer, "setEnabled",
                              Qt::QueuedConnection, Q_ARG(bool, paramEnabled));
  }

  if (!streamer->isEnabled()) return;

  // 空闲检测：3秒无客户端则零开销跳过
  qint64 lastClient = streamer->lastClientTime();
  if (lastClient > 0 && (QDateTime::currentMSecsSinceEpoch() - lastClient) > IDLE_TIMEOUT_MS) {
    return;
  }

  // 使用 QScreen::grabWindow(0) 直接读平台帧缓冲
  // 比 QWidget::grab() 更快：不触发 Widget 重绘，不阻塞渲染管线
  QScreen *screen = QGuiApplication::primaryScreen();
  if (!screen) return;
  QPixmap screenshot = screen->grabWindow(0);
  if (screenshot.isNull()) return;

  // 缩放到 960×540
  QPixmap scaled = screenshot.scaled(CAPTURE_WIDTH, CAPTURE_HEIGHT,
                                     Qt::KeepAspectRatio, Qt::FastTransformation);

  // JPEG 编码
  QByteArray jpeg;
  QBuffer buffer(&jpeg);
  buffer.open(QIODevice::WriteOnly);
  scaled.save(&buffer, "JPEG", JPEG_QUALITY);

  // 异步发送到流线程
  QMetaObject::invokeMethod(streamer, "setLatestFrame",
                            Qt::QueuedConnection, Q_ARG(QByteArray, jpeg));
}
