/**
 * screenstreamer.cc - 屏幕实时流服务实现（只读预览）
 *
 * HTTP 端点：
 *   GET /              返回 HTML 页面（只读 MJPEG 预览）
 *   GET /stream         MJPEG 流推送（multipart/x-mixed-replace，长连接）
 *   GET /frame.jpg     返回最新 JPEG 截图（向后兼容）
 *   GET /toggle        切换开关状态
 *   GET /status        返回 JSON 状态信息
 */

#include "selfdrive/ui/qt/screenstreamer.h"

#include <QDateTime>

ScreenStreamer::ScreenStreamer(QObject *parent)
    : QObject(parent) {}

ScreenStreamer::~ScreenStreamer() {
  stop();
}

void ScreenStreamer::start(int port) {
  if (server) return;

  port_ = port;
  server = new QTcpServer(this);
  connect(server, &QTcpServer::newConnection, this, &ScreenStreamer::onNewConnection);

  if (server->listen(QHostAddress::Any, port_)) {
    qInfo() << "ScreenStreamer: listening on port" << port_;
  } else {
    qWarning() << "ScreenStreamer: failed to listen on port" << port_
               << "-" << server->errorString();
  }
}

void ScreenStreamer::stop() {
  // 关闭所有 MJPEG 流客户端
  {
    QMutexLocker locker(&streamMutex_);
    for (QTcpSocket *client : streamClients_) {
      client->close();
      client->deleteLater();
    }
    streamClients_.clear();
  }

  if (server) {
    server->close();
    delete server;
    server = nullptr;
  }
}

void ScreenStreamer::setLatestFrame(const QByteArray &jpegData) {
  {
    QMutexLocker locker(&mutex);
    latestFrameJpeg = jpegData;
    lastFrameSize_ = jpegData.size();
    lastFrameTime_ = QDateTime::currentMSecsSinceEpoch();
    frameCount_++;
  }

  // 推送到所有 MJPEG 流客户端
  pushToAllStreamClients(jpegData);
}

void ScreenStreamer::setEnabled(bool en) {
  enabled_.store(en ? 1 : 0);
  qInfo() << "ScreenStreamer:" << (en ? "enabled" : "disabled");
}

bool ScreenStreamer::isEnabled() const {
  return enabled_.load() == 1;
}

void ScreenStreamer::touchClient() {
  lastClientTime_.store(QDateTime::currentMSecsSinceEpoch());
}

qint64 ScreenStreamer::lastClientTime() const {
  return lastClientTime_.load();
}

// ========== MJPEG 流推送 ==========

void ScreenStreamer::pushToAllStreamClients(const QByteArray &jpegData) {
  QMutexLocker locker(&streamMutex_);
  if (streamClients_.isEmpty()) return;

  // MJPEG multipart 帧格式
  QByteArray frame;
  frame.append("--FRAME\r\n");
  frame.append("Content-Type: image/jpeg\r\n");
  frame.append("Content-Length: ");
  frame.append(QByteArray::number(jpegData.size()));
  frame.append("\r\n\r\n");
  frame.append(jpegData);
  frame.append("\r\n");

  QSet<QTcpSocket*> deadClients;
  for (QTcpSocket *client : streamClients_) {
    if (client->state() == QAbstractSocket::ConnectedState) {
      qint64 written = client->write(frame);
      if (written < 0) {
        deadClients.insert(client);
      }
    } else {
      deadClients.insert(client);
    }
  }

  // 清理断开的客户端
  for (QTcpSocket *client : deadClients) {
    streamClients_.remove(client);
    client->deleteLater();
    emit streamClientDisconnected();
  }
}

void ScreenStreamer::serveMJPEGStream(QTcpSocket *socket) {
  // 发送 MJPEG 流响应头
  static const QByteArray streamHeader =
      "HTTP/1.1 200 OK\r\n"
      "Content-Type: multipart/x-mixed-replace; boundary=FRAME\r\n"
      "Connection: keep-alive\r\n"
      "Cache-Control: no-cache, no-store, must-revalidate\r\n"
      "Pragma: no-cache\r\n"
      "Expires: 0\r\n"
      "Access-Control-Allow-Origin: *\r\n"
      "\r\n"
      "--FRAME\r\n";  // 第一个 boundary，让浏览器开始解析

  socket->write(streamHeader);

  // 立即推送最新帧（如果有）
  {
    QMutexLocker locker(&mutex);
    if (!latestFrameJpeg.isEmpty()) {
      QByteArray initFrame;
      initFrame.append("Content-Type: image/jpeg\r\n");
      initFrame.append("Content-Length: ");
      initFrame.append(QByteArray::number(latestFrameJpeg.size()));
      initFrame.append("\r\n\r\n");
      initFrame.append(latestFrameJpeg);
      initFrame.append("\r\n");
      socket->write(initFrame);
    }
  }

  // 加入 MJPEG 客户端列表
  {
    QMutexLocker locker(&streamMutex_);
    streamClients_.insert(socket);
    emit streamClientConnected();
  }

  // 监听客户端断开
  connect(socket, &QTcpSocket::disconnected, this, [this, socket]() {
    QMutexLocker locker(&streamMutex_);
    streamClients_.remove(socket);
    socket->deleteLater();
    emit streamClientDisconnected();
  });

  qInfo() << "ScreenStreamer: MJPEG stream client connected (total:"
          << streamClients_.size() << ")";
}

// ========== 连接处理 ==========

void ScreenStreamer::onNewConnection() {
  touchClient();
  while (server && server->hasPendingConnections()) {
    QTcpSocket *socket = server->nextPendingConnection();
    connect(socket, &QTcpSocket::readyRead, this, [this, socket]() {
      if (socket->bytesAvailable() < 4) return;

      QByteArray data = socket->readAll();
      QString request = QString::fromUtf8(data);

      if (request.startsWith("GET /stream")) {
        serveMJPEGStream(socket);
      } else if (request.startsWith("GET /frame.jpg")) {
        serveFrameJpeg(socket);
      } else if (request.startsWith("GET /toggle")) {
        serveToggle(socket);
      } else if (request.startsWith("GET /status")) {
        serveStatus(socket);
      } else if (request.startsWith("GET /")) {
        serveHtml(socket);
      } else {
        serveJson(socket, "{\"error\":\"not found\"}");
      }
    });
  }
}

int ScreenStreamer::streamClientCount() {
  QMutexLocker locker(&streamMutex_);
  return streamClients_.size();
}

// ========== 开关切换 ==========

void ScreenStreamer::serveToggle(QTcpSocket *socket) {
  bool cur = isEnabled();
  setEnabled(!cur);
  serveJson(socket, QString("{\"enabled\":%1}").arg(!cur ? "true" : "false"));
}

// ========== 状态查询 ==========

void ScreenStreamer::serveStatus(QTcpSocket *socket) {
  QMutexLocker locker(&mutex);
  int fps = 0;
  if (lastFrameTime_ > 0) {
    qint64 elapsed = QDateTime::currentMSecsSinceEpoch() - lastFrameTime_;
    if (elapsed > 0) fps = 1000 / (int)elapsed;
  }
  int streamCount = 0;
  {
    QMutexLocker slocker(&streamMutex_);
    streamCount = streamClients_.size();
  }
  QString json = QString(
      "{\"enabled\":%1,\"fps\":%2,\"size\":%3,"
      "\"resolution\":\"960x540\",\"stream_clients\":%4}")
      .arg(isEnabled() ? "true" : "false")
      .arg(fps)
      .arg(lastFrameSize_)
      .arg(streamCount);
  serveJson(socket, json);
}

// ========== JSON 响应 ==========

void ScreenStreamer::serveJson(QTcpSocket *socket, const QString &json) {
  QByteArray body = json.toUtf8();
  QByteArray header = QByteArray(
      "HTTP/1.1 200 OK\r\n"
      "Content-Type: application/json; charset=utf-8\r\n"
      "Connection: close\r\n"
      "Access-Control-Allow-Origin: *\r\n"
      "Content-Length: ") + QByteArray::number(body.size()) + "\r\n\r\n";
  socket->write(header);
  socket->write(body);
  socket->disconnectFromHost();
}

// ========== HTML 页面（只读 MJPEG 预览） ==========

void ScreenStreamer::serveHtml(QTcpSocket *socket) {
  static const char *html =
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: text/html; charset=utf-8\r\n"
    "Connection: close\r\n"
    "Cache-Control: no-cache\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "\r\n"
    "<!DOCTYPE html>\n"
    "<html lang=\"zh\">\n"
    "<head>\n"
    "<meta charset=\"UTF-8\">\n"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no\">\n"
    "<style>\n"
    "*{margin:0;padding:0;box-sizing:border-box}\n"
    "html,body{width:100%;height:100%;overflow:hidden;"
    "background:#1a1a2e;-webkit-user-select:none;user-select:none}\n"
    ".wrap{display:flex;align-items:center;justify-content:center;"
    "width:100%;height:100%;position:relative}\n"
    "#f{max-width:100%;max-height:100%;object-fit:contain}\n"
    ".loader{position:absolute;width:28px;height:28px;border:2.5px solid #1e293b;"
    "border-top-color:#0d9488;border-radius:50%;animation:spin .7s linear infinite}\n"
    "@keyframes spin{to{transform:rotate(360deg)}}\n"
    "</style>\n"
    "</head>\n"
    "<body>\n"
    "<div class=\"wrap\" id=\"wrap\">\n"
    "<div class=\"loader\" id=\"ld\"></div>\n"
    "<img id=\"f\" src=\"/stream\" onload=\"this.style.display='';"
    "document.getElementById('ld').style.display='none'\" style=\"display:none\">\n"
    "</div>\n"
    "</body>\n"
    "</html>\n";

  socket->write(html);
  socket->disconnectFromHost();
}

// ========== JPEG 帧服务（向后兼容：单帧请求） ==========

void ScreenStreamer::serveFrameJpeg(QTcpSocket *socket) {
  if (!isEnabled()) {
    socket->write("HTTP/1.1 503 Service Unavailable\r\n"
                  "Content-Length: 0\r\n"
                  "Access-Control-Allow-Origin: *\r\n\r\n");
    socket->disconnectFromHost();
    return;
  }

  QMutexLocker locker(&mutex);
  QByteArray frame = latestFrameJpeg;

  if (frame.isEmpty()) {
    socket->write("HTTP/1.1 503 Service Unavailable\r\n"
                  "Content-Length: 0\r\n"
                  "Cache-Control: no-cache\r\n"
                  "Access-Control-Allow-Origin: *\r\n\r\n");
  } else {
    QByteArray header = QByteArray("HTTP/1.1 200 OK\r\n"
                                   "Content-Type: image/jpeg\r\n"
                                   "Content-Length: ") +
                        QByteArray::number(frame.size()) +
                        QByteArray("\r\n"
                                   "Cache-Control: no-cache,no-store,must-revalidate\r\n"
                                   "Pragma: no-cache\r\n"
                                   "Expires: 0\r\n"
                                   "Access-Control-Allow-Origin: *\r\n\r\n");
    socket->write(header);
    socket->write(frame);
  }
  socket->disconnectFromHost();
}
