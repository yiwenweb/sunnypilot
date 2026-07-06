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
  // 返回一个 HTML 页面，用 JavaScript 轮询 /frame.jpg
  // 针对移动端竖屏查看横屏 C3 画面的场景做了适配
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
    "background:#1a1a2e;font-family:-apple-system,BlinkMacSystemFont,sans-serif}\n"
    ".wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;"
    "width:100%;height:100%;position:relative}\n"
    ".img-area{flex:1;display:flex;align-items:center;justify-content:center;"
    "width:100%;overflow:hidden;position:relative}\n"
    "#f{max-width:100%;max-height:100%;object-fit:contain;"
    "opacity:0;transition:opacity .15s ease}\n"
    "#f.loaded{opacity:1}\n"
    ".status{position:absolute;bottom:8px;right:12px;"
    "color:#475569;font-size:11px;letter-spacing:.5px;pointer-events:none}\n"
    ".loader{position:absolute;width:28px;height:28px;border:2.5px solid #1e293b;"
    "border-top-color:#0d9488;border-radius:50%;animation:spin .7s linear infinite}\n"
    "@keyframes spin{to{transform:rotate(360deg)}}\n"
    "</style>\n"
    "</head>\n"
    "<body>\n"
    "<div class=\"wrap\">\n"
    "<div class=\"img-area\">\n"
    "<div class=\"loader\" id=\"ld\"></div>\n"
    "<img id=\"f\" src=\"/frame.jpg\" onload=\"this.classList.add('loaded');"
    "document.getElementById('ld').style.display='none'\">\n"
    "<div class=\"status\" id=\"st\">C3 LIVE</div>\n"
    "</div>\n"
    "</div>\n"
    "<script>\n"
    "var t=150;\n"
    "function r(){\n"
    "var n=new Image();\n"
    "n.onload=function(){\n"
    "var f=document.getElementById('f');f.src=n.src;\n"
    "document.getElementById('st').textContent='C3 LIVE';\n"
    "};\n"
    "n.onerror=function(){\n"
    "document.getElementById('st').textContent='WAITING...';\n"
    "};\n"
    "n.src='/frame.jpg?_='+Date.now();\n"
    "}\n"
    "setInterval(r,t);\n"
    "</script>\n"
    "</body>\n"
    "</html>\n";

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
