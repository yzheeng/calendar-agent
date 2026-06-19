import asyncio
import json
import math
import sys
import threading

import websockets
from PySide6.QtCore import Qt, QObject, QPointF, QRectF, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLayout,
    QLineEdit,
    QMenu,
    QVBoxLayout,
    QWidget,
)


WS_URL = "ws://127.0.0.1:8765/ws"
ORB_SIZE = 56          # 圆球本体直径
ORB_PADDING = 18       # 外圈给波纹 / 转圈留的余量
DRAG_THRESHOLD = 5
ANIM_INTERVAL_MS = 33  # ~30fps

ORB_BLUE = QColor("#4a90e2")
ORB_RED = QColor("#e74c3c")


class OrbWidget(QWidget):
    """单色 orb + 用动作（波纹 / 转圈 / 脉动）区分状态。"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        side = ORB_SIZE + 2 * ORB_PADDING
        self.setFixedSize(side, side)
        # 让点击穿透到 PetWindow 统一处理
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._state = "idle"
        self._phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(ANIM_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)

    def set_state(self, state: str) -> None:
        if state == self._state:
            return
        self._state = state
        self._phase = 0.0
        if state in {"listening", "thinking", "speaking"}:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

    def _tick(self) -> None:
        self._phase += ANIM_INTERVAL_MS / 1000.0
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cx = self.width() / 2
        cy = self.height() / 2
        r = ORB_SIZE / 2

        if self._state == "listening":
            self._paint_ripples(p, cx, cy, r)
        elif self._state == "thinking":
            self._paint_spinner(p, cx, cy, r)

        self._paint_orb(p, cx, cy, r)

    def _paint_orb(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        color = ORB_RED if self._state == "error" else ORB_BLUE
        # 说话时温和脉动
        scale = 1.0
        if self._state == "speaking":
            scale = 1.0 + 0.06 * math.sin(self._phase * 2 * math.pi * 1.2)
        rr = r * scale

        grad = QRadialGradient(cx - rr * 0.3, cy - rr * 0.3, rr * 1.5)
        grad.setColorAt(0.0, color.lighter(160))
        grad.setColorAt(0.55, color)
        grad.setColorAt(1.0, color.darker(150))
        p.setBrush(QBrush(grad))
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        p.drawEllipse(QPointF(cx, cy), rr, rr)

    def _paint_ripples(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        # 两道交错的波纹，从 orb 边缘向外扩张并淡出
        period = 1.4  # 秒
        for i in range(2):
            t = ((self._phase / period) + i * 0.5) % 1.0
            radius = r * (1.0 + t * 1.2)
            alpha = int(140 * (1.0 - t))
            if alpha <= 0:
                continue
            pen = QPen(QColor(ORB_BLUE.red(), ORB_BLUE.green(), ORB_BLUE.blue(), alpha), 2)
            p.setBrush(Qt.NoBrush)
            p.setPen(pen)
            p.drawEllipse(QPointF(cx, cy), radius, radius)

    def _paint_spinner(self, p: QPainter, cx: float, cy: float, r: float) -> None:
        outer_r = r + 8
        arc_span = 110  # 弧度跨度，度
        start_deg = (self._phase * 240) % 360  # 每秒 240°
        pen = QPen(QColor(ORB_BLUE.red(), ORB_BLUE.green(), ORB_BLUE.blue(), 220), 3)
        pen.setCapStyle(Qt.RoundCap)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        rect = QRectF(cx - outer_r, cy - outer_r, outer_r * 2, outer_r * 2)
        # QPainter angles: 16 = 1°, 0 = 3 点钟方向，逆时针为正
        p.drawArc(rect, int(-start_deg * 16), int(-arc_span * 16))


class WsClient(QObject):
    event_received = Signal(dict)

    def __init__(self):
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._ws = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_and_listen())
        finally:
            self._loop.close()

    async def _connect_and_listen(self):
        try:
            async with websockets.connect(WS_URL) as ws:
                self._ws = ws
                async for raw in ws:
                    self.event_received.emit(json.loads(raw))
        except Exception as e:
            self.event_received.emit({"type": "error", "message": f"连接失败: {e}"})
        finally:
            self._ws = None

    def send_json(self, obj: dict):
        if self._loop is None or self._ws is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._ws.send(json.dumps(obj)),
            self._loop,
        )

    def send_text(self, content: str):
        self.send_json({"type": "text", "content": content})

    def stop(self):
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread.is_alive():
            self._thread.join(timeout=2)


class PetWindow(QWidget):
    def __init__(self, client: WsClient):
        super().__init__()
        self.client = client
        self._latest_status = "等待连接…"

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.orb = OrbWidget(self)

        self.panel = QFrame()
        self.panel.setStyleSheet(
            "QFrame {"
            " background-color: rgba(30, 30, 40, 230);"
            " border-radius: 12px;"
            "}"
        )

        self.bubble = QLabel(self._latest_status)
        self.bubble.setWordWrap(True)
        self.bubble.setStyleSheet(
            "color: #f0f0f0; font-size: 13px; padding: 2px;"
        )
        self.bubble.setAttribute(Qt.WA_TransparentForMouseEvents)

        self.input = QLineEdit()
        self.input.setPlaceholderText("说点什么，回车发送")
        self.input.setStyleSheet(
            "QLineEdit {"
            " background-color: rgba(255, 255, 255, 30);"
            " color: #ffffff;"
            " border: 1px solid rgba(255, 255, 255, 60);"
            " border-radius: 8px;"
            " padding: 6px 10px;"
            " selection-background-color: #4a90e2;"
            "}"
        )
        self.input.returnPressed.connect(self._on_send)

        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(8)
        panel_layout.addWidget(self.bubble)
        panel_layout.addWidget(self.input)
        self.panel.setFixedWidth(260)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)
        root.addWidget(self.orb, alignment=Qt.AlignHCenter)
        root.addWidget(self.panel)
        root.setSizeConstraint(QLayout.SetFixedSize)

        self.panel.hide()

        self._press_pos = None
        self._drag_offset = None
        self._dragging = False
        self._recording = False

    def on_event(self, ev: dict):
        t = ev.get("type")
        if t == "ready":
            self._latest_status = f"已就绪（{ev.get('model')}）"
            self.bubble.setText(self._latest_status)
        elif t == "state":
            v = ev.get("value")
            self.orb.set_state(v)
            if v == "listening":
                self._latest_status = "聆听中…"
                self.bubble.setText(self._latest_status)
                self.input.setDisabled(True)
                self._recording = True
            elif v == "thinking":
                self._latest_status = "思考中…"
                self.bubble.setText(self._latest_status)
                self.input.setDisabled(True)
            elif v == "speaking":
                self._latest_status = "说话中…"
                self.bubble.setText(self._latest_status)
                self.input.setDisabled(True)
            elif v == "idle":
                self.input.setDisabled(False)
                self._recording = False
                if self.panel.isVisible():
                    self.input.setFocus()
        elif t == "transcript":
            self._latest_status = f"你说：{ev.get('content', '')}"
            self.bubble.setText(self._latest_status)
        elif t == "tool":
            self._latest_status = f"正在调用 {ev.get('name')}…"
            self.bubble.setText(self._latest_status)
        elif t == "reply":
            self._latest_status = ev.get("content", "")
            self.bubble.setText(self._latest_status)
        elif t == "error":
            self.orb.set_state("error")
            self._latest_status = f"⚠ {ev.get('message')}"
            self.bubble.setText(self._latest_status)
            self.input.setDisabled(False)
            self._recording = False

    def _toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.bubble.setText(self._latest_status)
            self.panel.show()
            self.input.setFocus()

    def _toggle_voice(self):
        if self._recording:
            self.client.send_json({"type": "voice_stop"})
        else:
            self.client.send_json({"type": "voice_start"})

    def _on_send(self):
        text = self.input.text().strip()
        if not text:
            return
        self.client.send_text(text)
        self.input.clear()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
            self._dragging = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._press_pos is None or not (e.buttons() & Qt.LeftButton):
            return
        cur = e.globalPosition().toPoint()
        if not self._dragging and (cur - self._press_pos).manhattanLength() > DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging:
            self.move(cur - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e):
        if self._press_pos is not None and not self._dragging:
            self._toggle_voice()
        self._press_pos = None
        self._drag_offset = None
        self._dragging = False
        e.accept()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        cli_action = menu.addAction("cli")
        quit_action = menu.addAction("退出")
        chosen = menu.exec(e.globalPos())
        if chosen is cli_action:
            self._toggle_panel()
        elif chosen is quit_action:
            QApplication.quit()


def main():
    app = QApplication(sys.argv)
    client = WsClient()
    window = PetWindow(client)
    client.event_received.connect(window.on_event)
    client.start()
    window.show()
    app.aboutToQuit.connect(client.stop)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
