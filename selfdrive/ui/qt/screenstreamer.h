/**
 * screenstreamer.h - 屏幕实时流服务
 *
 * 在 C3 Qt UI 进程中嵌入轻量 HTTP 服务器，提供：
 * - MJPEG 流式推送（/stream，multipart/x-mixed-replace）
 * - 实时屏幕截图（/frame.jpg，向后兼容）
 * - 反向触控注入（/touch）
 * - 开关控制（/toggle /status）
 *
 * 设计要点：
 * - 运行在独立 QThread 中，不影响 UI 渲染主线程
 * - MJPEG 长连接推送，WebView 无需 JS 轮询
 * - 可选 V4L2 硬件 JPEG 编码（骁龙 845 Venus）
 * - 空闲检测：3秒无客户端自动暂停抓帧
 */

#pragma once

#include <QObject>
#include <QThread>
#include <QTcpServer>
#include <QTcpSocket>
#include <QMutex>
#include <QSet>
#include <QByteArray>
#include <QAtomicInt>

class QWidget;
class V4L2JPEGEncoder;

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
  Q_INVOKABLE qint64 lastClientTime() const;
  Q_INVOKABLE int streamClientCount() const;
  void touchClient();

signals:
  void streamClientConnected();
  void streamClientDisconnected();

private slots:
  void onNewConnection();

private:
  // HTTP 请求分发
  void serveHtml(QTcpSocket *socket);
  void serveFrameJpeg(QTcpSocket *socket);
  void serveTouch(QTcpSocket *socket, const QString &query);
  void serveToggle(QTcpSocket *socket);
  void serveStatus(QTcpSocket *socket);
  void serveJson(QTcpSocket *socket, const QString &json);

  // MJPEG 流推送（长连接）
  void serveMJPEGStream(QTcpSocket *socket);

  // 将最新帧推送到所有 MJPEG 客户端
  void pushToAllStreamClients(const QByteArray &jpegData);

  // 触控注入
  void injectTouchEvent(int x, int y, bool pressed);
  void injectMouseMove(int x, int y);

  QTcpServer *server = nullptr;
  QMutex mutex;
  QByteArray latestFrameJpeg;
  int port_ = 8083;
  QAtomicInt enabled_{0};  // 默认关闭，由 ScreenStreamEnabled 参数控制
  QWidget *targetWidget_ = nullptr;

  // MJPEG 流客户端管理
  QSet<QTcpSocket*> streamClients_;
  QMutex streamMutex_;

  // 统计信息
  int frameCount_ = 0;
  int lastFrameSize_ = 0;
  qint64 lastFrameTime_ = 0;
  QAtomicInt lastClientTime_{0};
};
