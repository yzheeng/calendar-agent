import asyncio
import json
import sys
import threading

import websockets
from PySide6.QtCore import Qt, QObject, Signal
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
ORB_SIZE = 56
DRAG_THRESHOLD = 5

ORB_BASE = (
    "border-radius: {r}px;"
    "border: 1px solid rgba(255, 255, 255, 90);"
).format(r=ORB_SIZE // 2)

ORB_IDLE = ORB_BASE + (
    "background: qradialgradient(cx:0.3, cy:0.3, radius:0.95, fx:0.3, fy:0.3,"
    " stop:0 #a8d0ff, stop:0.55 #4a90e2, stop:1 #1f5eb8);"
)
ORB_THINKING = ORB_BASE + (
    "background: qradialgradient(cx:0.3, cy:0.3, radius:0.95, fx:0.3, fy:0.3,"
    " stop:0 #e2c7ff, stop:0.55 #9b59b6, stop:1 #5e2a82);"
)
ORB_ERROR = ORB_BASE + (
    "background: qradialgradient(cx:0.3, cy:0.3, radius:0.95, fx:0.3, fy:0.3,"
    " stop:0 #ffb3b3, stop:0.55 #e74c3c, stop:1 #8b1a0e);"
)


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

    def send_text(self, content: str):
        if self._loop is None or self._ws is None:
            return
        asyncio.run_coroutine_threadsafe(
            self._ws.send(json.dumps({"type": "text", "content": content})),
            self._loop,
        )

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

        self.orb = QLabel()
        self.orb.setFixedSize(ORB_SIZE, ORB_SIZE)
        self.orb.setStyleSheet(ORB_IDLE)
        # 让鼠标事件穿到 PetWindow，由它统一处理点击/拖动
        self.orb.setAttribute(Qt.WA_TransparentForMouseEvents)

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

    def on_event(self, ev: dict):
        t = ev.get("type")
        if t == "ready":
            self._latest_status = f"已就绪（{ev.get('model')}）"
            self.bubble.setText(self._latest_status)
        elif t == "state":
            v = ev.get("value")
            if v == "thinking":
                self.orb.setStyleSheet(ORB_THINKING)
                self._latest_status = "思考中…"
                self.bubble.setText(self._latest_status)
                self.input.setDisabled(True)
            elif v == "idle":
                self.orb.setStyleSheet(ORB_IDLE)
                self.input.setDisabled(False)
                if self.panel.isVisible():
                    self.input.setFocus()
        elif t == "tool":
            self._latest_status = f"正在调用 {ev.get('name')}…"
            self.bubble.setText(self._latest_status)
        elif t == "reply":
            self._latest_status = ev.get("content", "")
            self.bubble.setText(self._latest_status)
            self.input.setDisabled(False)
        elif t == "error":
            self.orb.setStyleSheet(ORB_ERROR)
            self._latest_status = f"⚠ {ev.get('message')}"
            self.bubble.setText(self._latest_status)
            self.input.setDisabled(False)

    def _toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.bubble.setText(self._latest_status)
            self.panel.show()
            self.input.setFocus()

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
            self._toggle_panel()
        self._press_pos = None
        self._drag_offset = None
        self._dragging = False
        e.accept()

    def contextMenuEvent(self, e):
        menu = QMenu(self)
        quit_action = menu.addAction("退出")
        quit_action.triggered.connect(QApplication.quit)
        menu.exec(e.globalPos())


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
