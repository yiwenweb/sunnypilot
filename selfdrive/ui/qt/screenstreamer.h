/**
 * screenstreamer.h - 屏幕实时流服务
 *
 * 在 C3 Qt UI 进程中嵌入一个轻量 HTTP 服务器，对外提供
 * 实时屏幕截图（MJPEG），供 Android 工具箱的"视频预览"功能使用。
 *
 * 设计要点：
 * - 运行在独立 QThread 中，不影响 UI 渲染主线程
 * - paintGL() 中以低频率（~6.7Hz）抓帧，最小化 GPU 读回开销
 * - 抓帧缩放至 50%（1080x540），大幅减少编码和网络传输量
 * - 仅在有客户端连接时才真正抓帧（按需启动）
 */

#pragma once

#include <QObject>
#include <QThread>
#include <QTcpServer>
#include <QTcpSocket>
#include <QMutex>
#include <QByteArray>

class ScreenStreamer : public QObject {
  Q_OBJECT

public:
  explicit ScreenStreamer(QObject *parent = nullptr);
  ~ScreenStreamer();

  Q_INVOKABLE void start(int port = 8083);
  Q_INVOKABLE void stop();
  Q_INVOKABLE void setLatestFrame(const QByteArray &jpegData);

private slots:
  void onNewConnection();

private:
  void serveHtml(QTcpSocket *socket);
  void serveFrameJpeg(QTcpSocket *socket);

  QTcpServer *server = nullptr;
  QMutex mutex;
  QByteArray latestFrameJpeg;
  int port_ = 8083;
};
