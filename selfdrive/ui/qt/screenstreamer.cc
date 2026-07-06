/**
 * screenstreamer.cc - 屏幕实时流服务实现
 *
 * HTTP 端点：
 *   GET /           返回 HTML 页面（含 JS 轮询，显示最新帧）
 *   GET /frame.jpg  返回最新的 JPEG 截图
 *
 * 线程安全：latestFrameJpeg 由 setLatestFrame (GUI 线程) 写入，
 * onNewConnection 回调 (Network 线程) 读取，通过 QMutex 保护。
 */

#include "selfdrive/ui/qt/screenstreamer.h"

ScreenStreamer::ScreenStreamer(QObject *parent)
    : QObject(parent) {}

ScreenStreamer::~ScreenStreamer() {
  stop();
}

void ScreenStreamer::start(int port) {
  if (server) return;  // already started

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
  if (server) {
    server->close();
    delete server;
    server = nullptr;
  }
}

void ScreenStreamer::setLatestFrame(const QByteArray &jpegData) {
  QMutexLocker locker(&mutex);
  latestFrameJpeg = jpegData;
}

void ScreenStreamer::onNewConnection() {
  while (server && server->hasPendingConnections()) {
    QTcpSocket *socket = server->nextPendingConnection();
    // 延迟解析请求：等数据到达后处理
    connect(socket, &QTcpSocket::readyRead, this, [this, socket]() {
      if (socket->bytesAvailable() < 4) return;

      QByteArray data = socket->readAll();
      QString request = QString::fromUtf8(data);

      // 解析 HTTP 请求行: GET /path HTTP/1.x
      if (request.startsWith("GET /frame.jpg")) {
        serveFrameJpeg(socket);
      } else if (request.startsWith("GET /")) {
        serveHtml(socket);
      } else {
        // 不支持的请求
        socket->write("HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n");
        socket->disconnectFromHost();
      }
    });

    // 超时断开
    connect(socket, &QTcpSocket::disconnected, socket, &QTcpSocket::deleteLater);
  }
}

void ScreenStreamer::serveHtml(QTcpSocket *socket) {
  // 返回一个 HTML 页面，用 JavaScript 每 120ms 轮询 /frame.jpg
  static const char *html =
    "HTTP/1.1 200 OK\r\n"
    "Content-Type: text/html; charset=utf-8\r\n"
    "Connection: close\r\n"
    "Cache-Control: no-cache\r\n"
    "Access-Control-Allow-Origin: *\r\n"
    "\r\n"
    "<!DOCTYPE html>\n"
    "<html><head>\n"
    "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no\">\n"
    "<style>html,body{margin:0;padding:0;background:#000;overflow:hidden;"
    "display:flex;align-items:center;justify-content:center;height:100vh;width:100vw}\n"
    "img{max-width:100%;max-height:100vh;object-fit:contain}</style>\n"
    "</head><body>\n"
    "<img id=\"f\" src=\"/frame.jpg\">\n"
    "<script>\n"
    "var t=120;\n"
    "function r(){document.getElementById('f').src='/frame.jpg?_='+Date.now()}\n"
    "setInterval(r,t);\n"
    "</script>\n"
    "</body></html>\n";

  socket->write(html);
  socket->disconnectFromHost();
}

void ScreenStreamer::serveFrameJpeg(QTcpSocket *socket) {
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
