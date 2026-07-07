/**
 * screenstreamer.cc - 屏幕实时流服务实现
 *
 * HTTP 端点：
 *   GET /              返回 HTML 页面（触控 + MJPEG 流）
 *   GET /stream         MJPEG 流推送（multipart/x-mixed-replace，长连接）
 *   GET /frame.jpg     返回最新 JPEG 截图（向后兼容）
 *   GET /touch?x=X&y=Y&action=press|release|move  反向触控注入
 *   GET /toggle        切换开关状态
 *   GET /status        返回 JSON 状态信息
 */

#include "selfdrive/ui/qt/screenstreamer.h"

#include <QApplication>
#include <QDateTime>
#include <QMouseEvent>
#include <QUrl>
#include <QUrlQuery>
#include <QWidget>

// 空闲超时：3秒无客户端连接则暂停抓帧
static const int IDLE_TIMEOUT_MS = 3000;

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
      } else if (request.startsWith("GET /touch")) {
        serveTouch(socket, request);
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

// ========== 触控注入 ==========

void ScreenStreamer::serveTouch(QTcpSocket *socket, const QString &request) {
  QString path = request.section(' ', 1, 1);
  QUrl url("http://localhost" + path);
  QUrlQuery query(url);

  int x = query.queryItemValue("x").toInt();
  int y = query.queryItemValue("y").toInt();
  QString action = query.queryItemValue("action");

  if (action == "press") {
    injectTouchEvent(x, y, true);
  } else if (action == "release") {
    injectTouchEvent(x, y, false);
  } else if (action == "move") {
    injectMouseMove(x, y);
  }

  serveJson(socket, "{\"ok\":true}");
}

void ScreenStreamer::setTargetWidget(QWidget *w) {
  targetWidget_ = w;
}

void ScreenStreamer::injectTouchEvent(int x, int y, bool pressed) {
  if (!targetWidget_) return;

  // 递归查找坐标所在的实际子控件（模拟 Qt 的 hit-test）
  QWidget *actualWidget = targetWidget_->childAt(x, y);
  if (!actualWidget) actualWidget = targetWidget_;

  // 转换为子控件的本地坐标
  QPointF localPos = actualWidget->mapFrom(targetWidget_, QPoint(x, y));

  if (pressed) {
    QMouseEvent *event = new QMouseEvent(
        QEvent::MouseButtonPress, localPos,
        Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
    QApplication::sendEvent(actualWidget, event);
  } else {
    QMouseEvent *event = new QMouseEvent(
        QEvent::MouseButtonRelease, localPos,
        Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
    QApplication::sendEvent(actualWidget, event);
  }
}

void ScreenStreamer::injectMouseMove(int x, int y) {
  if (!targetWidget_) return;

  QWidget *actualWidget = targetWidget_->childAt(x, y);
  if (!actualWidget) actualWidget = targetWidget_;

  QPointF localPos = actualWidget->mapFrom(targetWidget_, QPoint(x, y));

  QMouseEvent *event = new QMouseEvent(
      QEvent::MouseMove, localPos,
      Qt::NoButton, Qt::LeftButton, Qt::NoModifier);
  QApplication::sendEvent(actualWidget, event);
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

// ========== HTML 页面（MJPEG 流 + 触控） ==========

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
    "background:#1a1a2e;touch-action:none;-webkit-user-select:none;user-select:none}\n"
    ".wrap{display:flex;align-items:center;justify-content:center;"
    "width:100%;height:100%;position:relative}\n"
    "#f{max-width:100%;max-height:100%;object-fit:contain;"
    "touch-action:none;pointer-events:auto}\n"
    ".loader{position:absolute;width:28px;height:28px;border:2.5px solid #1e293b;"
    "border-top-color:#0d9488;border-radius:50%;animation:spin .7s linear infinite}\n"
    "@keyframes spin{to{transform:rotate(360deg)}}\n"
    ".touch-indicator{position:absolute;width:20px;height:20px;border-radius:50%;"
    "background:rgba(13,148,136,.4);border:2px solid #0d9488;pointer-events:none;"
    "transform:translate(-50%,-50%);opacity:0;transition:opacity .2s}\n"
    ".touch-indicator.active{opacity:1}\n"
    "</style>\n"
    "</head>\n"
    "<body>\n"
    "<div class=\"wrap\" id=\"wrap\">\n"
    "<div class=\"loader\" id=\"ld\"></div>\n"
    "<img id=\"f\" src=\"/stream\" onload=\"this.style.display='';"
    "document.getElementById('ld').style.display='none'\" style=\"display:none\">\n"
    "<div class=\"touch-indicator\" id=\"ti\"></div>\n"
    "</div>\n"
    "<script>\n"
    "var C3_W=1920,C3_H=1080;\n"
    "var touchDown=false,img=document.getElementById('f'),ti=document.getElementById('ti');\n"
    "\n"
    "// ===== 触控处理 =====\n"
    "function toC3(cx,cy){\n"
    "  var r=img.getBoundingClientRect();\n"
    "  return{x:Math.round((cx-r.left)/r.width*C3_W),"
    "          y:Math.round((cy-r.top)/r.height*C3_H)};\n"
    "}\n"
    "function showTouch(cx,cy,show){\n"
    "  var r=document.getElementById('wrap').getBoundingClientRect();\n"
    "  ti.style.left=(cx-r.left)+'px';ti.style.top=(cy-r.top)+'px';\n"
    "  ti.className='touch-indicator'+(show?' active':'');\n"
    "}\n"
    "function sendTouch(x,y,action){\n"
    "  fetch('/touch?x='+x+'&y='+y+'&action='+action).catch(function(){});\n"
    "}\n"
    "img.addEventListener('pointerdown',function(e){\n"
    "  e.preventDefault();\n"
    "  var c=toC3(e.clientX,e.clientY);\n"
    "  showTouch(e.clientX,e.clientY,true);\n"
    "  sendTouch(c.x,c.y,'press');\n"
    "  touchDown=true;\n"
    "  img.setPointerCapture(e.pointerId);\n"
    "},{passive:false});\n"
    "img.addEventListener('pointermove',function(e){\n"
    "  if(!touchDown) return;\n"
    "  e.preventDefault();\n"
    "  var c=toC3(e.clientX,e.clientY);\n"
    "  showTouch(e.clientX,e.clientY,true);\n"
    "  sendTouch(c.x,c.y,'move');\n"
    "},{passive:false});\n"
    "function up(e){\n"
    "  if(!touchDown) return;\n"
    "  var c=toC3(e.clientX,e.clientY);\n"
    "  showTouch(0,0,false);\n"
    "  sendTouch(c.x,c.y,'release');\n"
    "  touchDown=false;\n"
    "}\n"
    "img.addEventListener('pointerup',up);\n"
    "img.addEventListener('pointercancel',up);\n"
    "img.addEventListener('pointerleave',up);\n"
    "</script>\n"
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
