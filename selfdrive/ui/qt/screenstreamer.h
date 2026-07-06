/**
 * screenstreamer.h - 屏幕实时流服务
 *
 * 在 C3 Qt UI 进程中嵌入轻量 HTTP 服务器，提供：
 * - 实时屏幕截图（JPEG 轮询）
 * - 反向触控注入
 * - 开关控制（Params: ScreenStreamEnabled）
 *
 * 设计要点：
 * - 运行在独立 QThread 中，不影响 UI 渲染主线程
 * - 定时抓帧（~6.7Hz），缩放至 50%，JPEG 编码
 * - 触控通过 QMouseEvent 注入 Qt 事件系统
 */

#pragma once

#include <QObject>
#include <QThread>
#include <QTcpServer>
#include <QTcpSocket>
#include <QMutex>
#include <QByteArray>
#include <QAtomicInt>

class QWidget;

class ScreenStreamer : public QObject {
  Q_OBJECT

public:
  explicit ScreenStreamer(QObject *parent = nullptr);
  ~ScreenStreamer();

  Q_INVOKABLE void start(int port = 8083);
  Q_INVOKABLE void stop();
  Q_INVOKABLE void setLatestFrame(const QByteArray &jpegData);
  Q_INVOKABLE void setEnabled(bool en);
  Q_INVOKABLE bool isEnabled() const;
  Q_INVOKABLE void setTargetWidget(QWidget *w);

private slots:
  void onNewConnection();

private:
  void serveHtml(QTcpSocket *socket);
  void serveFrameJpeg(QTcpSocket *socket);
  void serveTouch(QTcpSocket *socket, const QString &query);
  void serveToggle(QTcpSocket *socket);
  void serveStatus(QTcpSocket *socket);
  void serveJson(QTcpSocket *socket, const QString &json);
  void injectTouchEvent(int x, int y, bool pressed);
  void injectMouseMove(int x, int y);

  QTcpServer *server = nullptr;
  QMutex mutex;
  QByteArray latestFrameJpeg;
  int port_ = 8083;
  QAtomicInt enabled_{1};  // 默认开启
  QWidget *targetWidget_ = nullptr;  // 主线程 widget，用于触控注入

  // 统计信息
  int frameCount_ = 0;
  int lastFrameSize_ = 0;
  qint64 lastFrameTime_ = 0;
};
