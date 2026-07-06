/**
 * screenstreamer.cc - 屏幕实时流服务实现
 *
 * HTTP 端点：
 *   GET /              返回 HTML 页面（触控 + 统计信息）
 *   GET /frame.jpg     返回最新的 JPEG 截图
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
  if (server) {
    server->close();
    delete server;
    server = nullptr;
  }
}

void ScreenStreamer::setLatestFrame(const QByteArray &jpegData) {
  QMutexLocker locker(&mutex);
  latestFrameJpeg = jpegData;
  lastFrameSize_ = jpegData.size();
  lastFrameTime_ = QDateTime::currentMSecsSinceEpoch();
  frameCount_++;
}

void ScreenStreamer::setEnabled(bool en) {
  enabled_.store(en ? 1 : 0);
  if (!en) {
    QMutexLocker locker(&mutex);
    latestFrameJpeg.clear();
  }
  qInfo() << "ScreenStreamer:" << (en ? "enabled" : "disabled");
}

bool ScreenStreamer::isEnabled() const {
  return enabled_.load() == 1;
}

void ScreenStreamer::onNewConnection() {
  while (server && server->hasPendingConnections()) {
    QTcpSocket *socket = server->nextPendingConnection();
    connect(socket, &QTcpSocket::readyRead, this, [this, socket]() {
      if (socket->bytesAvailable() < 4) return;

      QByteArray data = socket->readAll();
      QString request = QString::fromUtf8(data);

      if (request.startsWith("GET /frame.jpg")) {
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

    connect(socket, &QTcpSocket::disconnected, socket, &QTcpSocket::deleteLater);
  }
}

// ========== 触控注入 ==========

void ScreenStreamer::serveTouch(QTcpSocket *socket, const QString &request) {
  // 解析 URL 查询参数
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

  QPointF pos(x, y);
  if (pressed) {
    QMouseEvent *event = new QMouseEvent(
        QEvent::MouseButtonPress, pos,
        Qt::LeftButton, Qt::LeftButton, Qt::NoModifier);
    QApplication::postEvent(targetWidget_, event);
  } else {
    QMouseEvent *event = new QMouseEvent(
        QEvent::MouseButtonRelease, pos,
        Qt::LeftButton, Qt::NoButton, Qt::NoModifier);
    QApplication::postEvent(targetWidget_, event);
  }
}

void ScreenStreamer::injectMouseMove(int x, int y) {
  if (!targetWidget_) return;

  QPointF pos(x, y);
  QMouseEvent *event = new QMouseEvent(
      QEvent::MouseMove, pos,
      Qt::NoButton, Qt::LeftButton, Qt::NoModifier);
  QApplication::postEvent(targetWidget_, event);
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
  QString json = QString("{\"enabled\":%1,\"fps\":%2,\"size\":%3,\"resolution\":\"960x540\"}")
                     .arg(isEnabled() ? "true" : "false")
                     .arg(fps)
                     .arg(lastFrameSize_);
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

// ========== HTML 页面（含触控 + 统计信息） ==========

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
    "background:#1a1a2e;font-family:-apple-system,BlinkMacSystemFont,sans-serif;"
    "touch-action:none;-webkit-user-select:none;user-select:none}\n"
    ".wrap{display:flex;flex-direction:column;align-items:center;justify-content:center;"
    "width:100%;height:100%;position:relative}\n"
    ".img-area{flex:1;display:flex;align-items:center;justify-content:center;"
    "width:100%;overflow:hidden;position:relative}\n"
    "#f{max-width:100%;max-height:100%;object-fit:contain;opacity:0;transition:opacity .15s ease;"
    "touch-action:none;pointer-events:auto}\n"
    "#f.loaded{opacity:1}\n"
    ".info{position:absolute;top:8px;right:12px;"
    "color:#94a3b8;font-size:10px;text-align:right;pointer-events:none;"
    "background:rgba(15,23,42,.7);padding:4px 8px;border-radius:4px;line-height:1.5}\n"
    ".status{position:absolute;bottom:8px;right:12px;"
    "color:#475569;font-size:11px;pointer-events:none}\n"
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
    "<div class=\"wrap\">\n"
    "<div class=\"img-area\" id=\"imgArea\">\n"
    "<div class=\"loader\" id=\"ld\"></div>\n"
    "<img id=\"f\" src=\"/frame.jpg\" onload=\"this.classList.add('loaded');"
    "document.getElementById('ld').style.display='none'\">\n"
    "<div class=\"touch-indicator\" id=\"ti\"></div>\n"
    "<div class=\"info\" id=\"info\">1920×1080 | 0 KB | 0 fps</div>\n"
    "<div class=\"status\" id=\"st\">C3 LIVE</div>\n"
    "</div>\n"
    "</div>\n"
    "<script>\n"
    "var pollMs=150, fpsCounter=0, fpsTimer=0, curFps=0;\n"
    "var c3W=1920, c3H=1080;\n"
    "var touchDown=false;\n"
    "\n"
    "function r(){\n"
    "  var n=new Image();\n"
    "  n.onload=function(){\n"
    "    var f=document.getElementById('f');f.src=n.src;\n"
    "    document.getElementById('st').textContent='C3 LIVE';\n"
    "  };\n"
    "  n.onerror=function(){\n"
    "    document.getElementById('st').textContent='WAITING...';\n"
    "  };\n"
    "  var x=new XMLHttpRequest();\n"
    "  x.open('GET','/frame.jpg?_='+Date.now());\n"
    "  x.responseType='blob';\n"
    "  x.onload=function(){\n"
    "    if(this.response){\n"
    "      var sz=this.response.size;\n"
    "      fpsCounter++;\n"
    "      var now=Date.now();\n"
    "      if(!fpsTimer) fpsTimer=now;\n"
    "      if(now-fpsTimer>=1000){curFps=fpsCounter;fpsCounter=0;fpsTimer=now}\n"
    "      document.getElementById('info').textContent=\n"
    "        c3W+'x'+c3H+' | '+(sz/1024).toFixed(1)+' KB | '+curFps+' fps';\n"
    "    }\n"
    "  };\n"
    "  x.send();\n"
    "  n.src='/frame.jpg?_='+Date.now()+Math.random();\n"
    "}\n"
    "setInterval(r,pollMs);\n"
    "\n"
    "// ===== 触控处理 =====\n"
    "var img=document.getElementById('f');\n"
    "var ti=document.getElementById('ti');\n"
    "var area=document.getElementById('imgArea');\n"
    "\n"
    "function toC3Coords(clientX,clientY){\n"
    "  var r=img.getBoundingClientRect();\n"
    "  var rx=(clientX-r.left)/r.width;\n"
    "  var ry=(clientY-r.top)/r.height;\n"
    "  return{x:Math.round(rx*c3W),y:Math.round(ry*c3H)};\n"
    "}\n"
    "\n"
    "function showTouch(x,y,show){\n"
    "  ti.style.left=x+'px'; ti.style.top=y+'px';\n"
    "  ti.className='touch-indicator'+(show?' active':'');\n"
    "}\n"
    "\n"
    "function sendTouch(x,y,action){\n"
    "  fetch('/touch?x='+x+'&y='+y+'&action='+action).catch(function(){});\n"
    "}\n"
    "\n"
    "img.addEventListener('pointerdown',function(e){\n"
    "  e.preventDefault();\n"
    "  var c=toC3Coords(e.clientX,e.clientY);\n"
    "  var ar=area.getBoundingClientRect();\n"
    "  showTouch(e.clientX-ar.left+area.scrollLeft,"
    "           e.clientY-ar.top+area.scrollTop,true);\n"
    "  sendTouch(c.x,c.y,'press');\n"
    "  touchDown=true; touchStartTime=Date.now();\n"
    "  img.setPointerCapture(e.pointerId);\n"
    "},{passive:false});\n"
    "\n"
    "img.addEventListener('pointermove',function(e){\n"
    "  if(!touchDown) return;\n"
    "  e.preventDefault();\n"
    "  var c=toC3Coords(e.clientX,e.clientY);\n"
    "  var ar=area.getBoundingClientRect();\n"
    "  showTouch(e.clientX-ar.left+area.scrollLeft,"
    "           e.clientY-ar.top+area.scrollTop,true);\n"
    "  sendTouch(c.x,c.y,'move');\n"
    "},{passive:false});\n"
    "\n"
    "function touchEnd(e){\n"
    "  var c=toC3Coords(e.clientX,e.clientY);\n"
    "  showTouch(0,0,false);\n"
    "  sendTouch(c.x,c.y,'release');\n"
    "  touchDown=false;\n"
    "}\n"
    "img.addEventListener('pointerup',touchEnd);\n"
    "img.addEventListener('pointercancel',touchEnd);\n"
    "img.addEventListener('pointerleave',touchEnd);\n"
    "</script>\n"
    "</body>\n"
    "</html>\n";

  socket->write(html);
  socket->disconnectFromHost();
}

// ========== JPEG 帧服务 ==========

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
