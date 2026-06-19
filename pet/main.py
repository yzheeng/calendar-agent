import asyncio
import json
import math
import sys
import threading

import websockets
from PySide6.QtCore import Qt, QObject, QPointF, QRectF, QEvent, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMenu,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


WS_URL = "ws://127.0.0.1:8765/ws"
ORB_SIZE = 56          # 圆球本体直径
ORB_PADDING = 18       # 外圈给波纹 / 转圈留的余量
DRAG_THRESHOLD = 5
ANIM_INTERVAL_MS = 33  # ~30fps
TEXT_BOX_WIDTH = 430
TEXT_BOX_HEIGHT = 156

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


class SendTextEdit(QPlainTextEdit):
    send_requested = Signal(str)

    def keyPressEvent(self, event):
        is_enter = event.key() in (Qt.Key_Return, Qt.Key_Enter)
        wants_newline = bool(event.modifiers() & Qt.ShiftModifier)
        if is_enter and not wants_newline:
            text = self.toPlainText().strip()
            if text:
                self.send_requested.emit(text)
            event.accept()
            return
        super().keyPressEvent(event)


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
        self._ui_mode = "voice"

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.orb = OrbWidget(self)
        self.voice_status = QLabel("")
        self.voice_status.setAlignment(Qt.AlignCenter)
        self.voice_status.setWordWrap(True)
        self.voice_status.setStyleSheet(
            "QLabel {"
            " color: #f7f7f7;"
            " background-color: rgba(30, 30, 40, 220);"
            " border-radius: 10px;"
            " padding: 6px 10px;"
            " font-size: 13px;"
            "}"
        )
        self.voice_status.setFixedWidth(220)
        self.voice_status.hide()

        self.voice_status_timer = QTimer(self)
        self.voice_status_timer.setSingleShot(True)
        self.voice_status_timer.timeout.connect(self.voice_status.hide)

        self.voice_view = QWidget(self)
        voice_layout = QVBoxLayout(self.voice_view)
        voice_layout.setContentsMargins(4, 4, 4, 4)
        voice_layout.setSpacing(4)
        voice_layout.addWidget(self.orb, alignment=Qt.AlignHCenter)
        voice_layout.addWidget(self.voice_status, alignment=Qt.AlignHCenter)
        voice_layout.setSizeConstraint(QLayout.SetFixedSize)

        self.text_box = QFrame(self)
        self.text_box.setFixedSize(TEXT_BOX_WIDTH, TEXT_BOX_HEIGHT)
        self.text_box.setStyleSheet(
            "QFrame {"
            " background-color: rgba(255, 255, 255, 248);"
            " border: 1px solid rgba(0, 0, 0, 45);"
            " border-radius: 18px;"
            "}"
        )
        shadow = QGraphicsDropShadowEffect(self.text_box)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 48))
        self.text_box.setGraphicsEffect(shadow)

        self.title_label = QLabel("日历助手")
        self.title_label.setStyleSheet(
            "QLabel {"
            " background: transparent;"
            " border: none;"
            " color: #242424;"
            " font-size: 15px;"
            " font-weight: 600;"
            "}"
        )

        self.input = SendTextEdit()
        self.input.setFixedHeight(82)
        self.input.setPlaceholderText("问问日历助手")
        self.input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.input.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.input.mapToGlobal(pos))
        )
        self.input.setStyleSheet(
            "QPlainTextEdit {"
            " background-color: rgba(246, 247, 249, 255);"
            " color: #262626;"
            " border: 1px solid rgba(0, 0, 0, 28);"
            " border-radius: 12px;"
            " font-size: 16px;"
            " padding: 8px 10px;"
            " selection-background-color: #4a90e2;"
            "}"
            "QPlainTextEdit:focus {"
            " border: 1px solid rgba(74, 144, 226, 150);"
            " background-color: #ffffff;"
            "}"
            "QPlainTextEdit:disabled {"
            " color: #777777;"
            " background-color: rgba(242, 242, 242, 255);"
            "}"
        )
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.send_requested.connect(self._send_text)

        self.status_label = QLabel("等待连接")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setFixedWidth(96)
        self.status_label.setStyleSheet(
            "QLabel {"
            " background: transparent;"
            " border: none;"
            " color: #6b7280;"
            " font-size: 13px;"
            " font-weight: 500;"
            "}"
        )

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        title_row.addWidget(self.status_label)

        text_layout = QVBoxLayout(self.text_box)
        text_layout.setContentsMargins(16, 14, 16, 16)
        text_layout.setSpacing(12)
        text_layout.addLayout(title_row)
        text_layout.addWidget(self.input)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)
        root.addWidget(self.voice_view, alignment=Qt.AlignHCenter)
        root.addWidget(self.text_box, alignment=Qt.AlignHCenter)
        root.setSizeConstraint(QLayout.SetFixedSize)

        self.text_box.hide()
        self.text_box.installEventFilter(self)
        self.title_label.installEventFilter(self)
        self.status_label.installEventFilter(self)

        self._press_pos = None
        self._drag_offset = None
        self._dragging = False
        self._recording = False

    def on_event(self, ev: dict):
        t = ev.get("type")
        if t == "ready":
            self._latest_status = f"已就绪（{ev.get('model')}）"
            self._set_text_status("已就绪")
            self._show_voice_status(self._latest_status, 2500)
        elif t == "state":
            v = ev.get("value")
            self.orb.set_state(v)
            if v == "listening":
                self._latest_status = "聆听中…"
                self._set_text_status("聆听中")
                self._show_voice_status(self._latest_status, 0)
                self.input.setDisabled(True)
                self._recording = True
            elif v == "thinking":
                self._latest_status = "思考中…"
                self._set_text_status("思考中")
                self._show_voice_status(self._latest_status, 0)
                self.input.setDisabled(True)
            elif v == "speaking":
                self._latest_status = "说话中…"
                self._set_text_status("说话中")
                self._show_voice_status(self._latest_status, 0)
                self.input.setDisabled(True)
            elif v == "idle":
                self.input.setDisabled(False)
                self._recording = False
                self._set_text_status("就绪")
                self._hide_voice_status_later()
                if self._ui_mode == "text":
                    self.input.setFocus()
        elif t == "transcript":
            self._latest_status = f"你说：{ev.get('content', '')}"
            self._set_text_status("已转写")
            self._show_voice_status(self._latest_status, 2500)
        elif t == "tool":
            self._latest_status = f"正在调用 {ev.get('name')}…"
            self._set_text_status("工具中")
            self._show_voice_status(self._latest_status, 0)
        elif t == "reply":
            self._latest_status = ev.get("content", "")
            self._set_text_status("已回复")
            self._set_reply_placeholder(self._latest_status)
            self._show_voice_status(self._latest_status, 4500)
        elif t == "error":
            self.orb.set_state("error")
            self._latest_status = f"出错：{ev.get('message')}"
            self._set_text_status("出错")
            self._set_reply_placeholder(self._latest_status)
            self._show_voice_status(self._latest_status, 4500)
            self.input.setDisabled(False)
            self._recording = False

    def _switch_to_text_mode(self):
        if self._recording:
            self.client.send_json({"type": "voice_stop"})
            self._recording = False
        self._ui_mode = "text"
        self.voice_view.hide()
        self.text_box.show()
        self.orb.set_state("idle")
        self.input.setDisabled(False)
        self.input.setFocus()
        self.adjustSize()

    def _switch_to_voice_mode(self):
        self._ui_mode = "voice"
        self.text_box.hide()
        self.voice_view.show()
        if self._latest_status and self._latest_status != "等待连接…":
            self._show_voice_status(self._latest_status, 2500)
        self.adjustSize()

    def _clear_context(self):
        self.client.send_text("/clear_context")
        self._latest_status = "正在清除上下文…"
        self._set_text_status("清除中")
        self._show_voice_status(self._latest_status, 0)

    def _set_text_status(self, text: str) -> None:
        self.status_label.setText(text)

    def _set_reply_placeholder(self, text: str) -> None:
        compact = " ".join(text.split())
        if len(compact) > 36:
            compact = f"{compact[:36]}..."
        self.input.setPlaceholderText(compact or "问问日历助手")

    def _show_voice_status(self, text: str, timeout_ms: int) -> None:
        compact = " ".join(text.split())
        if len(compact) > 80:
            compact = f"{compact[:80]}..."
        self.voice_status.setText(compact)
        self.voice_status.show()
        if timeout_ms > 0:
            self.voice_status_timer.start(timeout_ms)
        else:
            self.voice_status_timer.stop()

    def _hide_voice_status_later(self) -> None:
        if self.voice_status.isVisible():
            self.voice_status_timer.start(1200)

    def _toggle_voice(self):
        if self._recording:
            self.client.send_json({"type": "voice_stop"})
        else:
            self.client.send_json({"type": "voice_start"})

    def _send_text(self, text: str):
        text = text.strip()
        if not text:
            return
        self.client.send_text(text)
        self._set_text_status("发送中")
        self.input.clear()

    def eventFilter(self, obj, event):
        if obj in {self.text_box, self.title_label, self.status_label}:
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.RightButton:
                self._show_context_menu(event.globalPosition().toPoint())
                event.accept()
                return True
            if event.type() == QEvent.Type.MouseButtonPress and event.button() == Qt.LeftButton:
                self._begin_drag(event.globalPosition().toPoint())
                event.accept()
                return True
            if event.type() == QEvent.Type.MouseMove and event.buttons() & Qt.LeftButton:
                self._continue_drag(event.globalPosition().toPoint())
                event.accept()
                return True
            if event.type() == QEvent.Type.MouseButtonRelease and self._press_pos is not None:
                self._end_drag()
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def _begin_drag(self, global_pos):
        self._press_pos = global_pos
        self._drag_offset = self._press_pos - self.frameGeometry().topLeft()
        self._dragging = False

    def _continue_drag(self, global_pos):
        if self._press_pos is None:
            return
        if not self._dragging and (global_pos - self._press_pos).manhattanLength() > DRAG_THRESHOLD:
            self._dragging = True
        if self._dragging:
            self.move(global_pos - self._drag_offset)

    def _end_drag(self):
        self._press_pos = None
        self._drag_offset = None
        self._dragging = False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._begin_drag(e.globalPosition().toPoint())
            e.accept()

    def mouseMoveEvent(self, e):
        if self._press_pos is None or not (e.buttons() & Qt.LeftButton):
            return
        self._continue_drag(e.globalPosition().toPoint())
        e.accept()

    def mouseReleaseEvent(self, e):
        if self._ui_mode == "voice" and self._press_pos is not None and not self._dragging:
            self._toggle_voice()
        self._end_drag()
        e.accept()

    def contextMenuEvent(self, e):
        self._show_context_menu(e.globalPos())
        e.accept()

    def _show_context_menu(self, global_pos):
        menu = QMenu(self)
        text_action = menu.addAction("文本模式")
        voice_action = menu.addAction("语音模式")
        clear_action = menu.addAction("清除上下文")
        menu.addSeparator()
        quit_action = menu.addAction("退出")
        chosen = menu.exec(global_pos)
        if chosen is text_action:
            self._switch_to_text_mode()
        elif chosen is voice_action:
            self._switch_to_voice_mode()
        elif chosen is clear_action:
            self._clear_context()
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
