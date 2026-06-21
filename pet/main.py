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
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


WS_URL = "ws://127.0.0.1:8765/ws"
ORB_SIZE = 56          # 圆球本体直径
ORB_PADDING = 18       # 外圈给波纹 / 转圈留的余量
DRAG_THRESHOLD = 5
ANIM_INTERVAL_MS = 33  # ~30fps

# 聊天面板尺寸
CHAT_PANEL_WIDTH = 380
CHAT_PANEL_HEIGHT = 480
BUBBLE_MAX_WIDTH = 268

ORB_BLUE = QColor("#4a90e2")
ORB_RED = QColor("#e74c3c")

USER_BUBBLE_QSS = (
    "QLabel {"
    " background-color: #4a90e2;"
    " color: #ffffff;"
    " border-radius: 14px;"
    " border-bottom-right-radius: 4px;"
    " padding: 9px 13px;"
    " font-size: 14px;"
    " line-height: 20px;"
    "}"
)
BOT_BUBBLE_QSS = (
    "QLabel {"
    " background-color: #eef0f3;"
    " color: #1f2933;"
    " border-radius: 14px;"
    " border-bottom-left-radius: 4px;"
    " padding: 9px 13px;"
    " font-size: 14px;"
    " line-height: 20px;"
    "}"
)
ERROR_BUBBLE_QSS = (
    "QLabel {"
    " background-color: #fdecea;"
    " color: #c0392b;"
    " border-radius: 14px;"
    " border-bottom-left-radius: 4px;"
    " padding: 9px 13px;"
    " font-size: 14px;"
    " line-height: 20px;"
    "}"
)


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

        # ===== 文本模式：chatbot 面板 =====
        self.text_box = QFrame(self)
        self.text_box.setFixedSize(CHAT_PANEL_WIDTH, CHAT_PANEL_HEIGHT)
        self.text_box.setStyleSheet(
            "QFrame#chatPanel {"
            " background-color: rgba(255, 255, 255, 250);"
            " border: 1px solid rgba(0, 0, 0, 40);"
            " border-radius: 18px;"
            "}"
        )
        self.text_box.setObjectName("chatPanel")
        shadow = QGraphicsDropShadowEffect(self.text_box)
        shadow.setBlurRadius(28)
        shadow.setOffset(0, 8)
        shadow.setColor(QColor(0, 0, 0, 55))
        self.text_box.setGraphicsEffect(shadow)

        # --- 头部：标题 + 状态，可拖动 ---
        self.title_label = QLabel("日历助手")
        self.title_label.setStyleSheet(
            "QLabel { background: transparent; border: none;"
            " color: #1f2933; font-size: 15px; font-weight: 600; }"
        )
        self.status_label = QLabel("● 等待连接")
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_label.setStyleSheet(
            "QLabel { background: transparent; border: none;"
            " color: #9aa3af; font-size: 12px; font-weight: 500; }"
        )

        self.chat_header = QWidget()
        self.chat_header.setStyleSheet("background: transparent;")
        header_row = QHBoxLayout(self.chat_header)
        header_row.setContentsMargins(18, 14, 16, 10)
        header_row.setSpacing(8)
        header_row.addWidget(self.title_label)
        header_row.addStretch(1)
        header_row.addWidget(self.status_label)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background-color: rgba(0, 0, 0, 22); border: none;")

        # --- 消息列表：可滚动 ---
        self.msg_container = QWidget()
        self.msg_container.setStyleSheet("background: transparent;")
        self.msg_layout = QVBoxLayout(self.msg_container)
        self.msg_layout.setContentsMargins(14, 14, 14, 14)
        self.msg_layout.setSpacing(10)
        self.msg_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.msg_container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 7px; margin: 4px 2px 4px 0; }"
            "QScrollBar::handle:vertical { background: rgba(0,0,0,55); border-radius: 3px; min-height: 28px; }"
            "QScrollBar::handle:vertical:hover { background: rgba(0,0,0,90); }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )

        # --- 底部输入区 ---
        self.input = SendTextEdit()
        self.input.setFixedHeight(60)
        self.input.setPlaceholderText("输入消息，Enter 发送 / Shift+Enter 换行")
        self.input.setContextMenuPolicy(Qt.CustomContextMenu)
        self.input.customContextMenuRequested.connect(
            lambda pos: self._show_context_menu(self.input.mapToGlobal(pos))
        )
        self.input.setStyleSheet(
            "QPlainTextEdit {"
            " background-color: #f4f5f7;"
            " color: #1f2933;"
            " border: 1px solid rgba(0, 0, 0, 24);"
            " border-radius: 14px;"
            " font-size: 14px;"
            " padding: 8px 12px;"
            " selection-background-color: #4a90e2;"
            "}"
            "QPlainTextEdit:focus {"
            " border: 1px solid rgba(74, 144, 226, 160);"
            " background-color: #ffffff;"
            "}"
            "QPlainTextEdit:disabled {"
            " color: #9aa3af;"
            " background-color: #f0f0f2;"
            "}"
        )
        self.input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.input.send_requested.connect(self._send_text)

        input_wrap = QWidget()
        input_wrap.setStyleSheet("background: transparent;")
        input_row = QVBoxLayout(input_wrap)
        input_row.setContentsMargins(14, 8, 14, 14)
        input_row.setSpacing(0)
        input_row.addWidget(self.input)

        text_layout = QVBoxLayout(self.text_box)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(0)
        text_layout.addWidget(self.chat_header)
        text_layout.addWidget(divider)
        text_layout.addWidget(self.scroll, 1)
        text_layout.addWidget(input_wrap)

        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(0)
        root.addWidget(self.voice_view, alignment=Qt.AlignHCenter)
        root.addWidget(self.text_box, alignment=Qt.AlignHCenter)
        root.setSizeConstraint(QLayout.SetFixedSize)

        self.text_box.hide()
        self.chat_header.installEventFilter(self)
        self.title_label.installEventFilter(self)
        self.status_label.installEventFilter(self)

        # 聊天状态
        self._thinking_row: QWidget | None = None
        self._thinking_label: QLabel | None = None
        self._thinking_base = "思考中"
        self._thinking_phase = 0
        self._thinking_timer = QTimer(self)
        self._thinking_timer.setInterval(420)
        self._thinking_timer.timeout.connect(self._tick_thinking)
        self._greeted = False

        self._press_pos = None
        self._drag_offset = None
        self._dragging = False
        self._recording = False

    def on_event(self, ev: dict):
        t = ev.get("type")
        if t == "ready":
            self._latest_status = f"已就绪（{ev.get('model')}）"
            self._set_text_status("已就绪", "#3aab6b")
            self._show_voice_status(self._latest_status, 2500)
        elif t == "state":
            v = ev.get("value")
            self.orb.set_state(v)
            if v == "listening":
                self._latest_status = "聆听中…"
                self._set_text_status("聆听中", "#4a90e2")
                self._show_voice_status(self._latest_status, 0)
                self.input.setDisabled(True)
                self._recording = True
            elif v == "thinking":
                self._latest_status = "思考中…"
                self._set_text_status("思考中", "#e0982f")
                self._show_voice_status(self._latest_status, 0)
                self.input.setDisabled(True)
                self._start_thinking("思考中")
            elif v == "speaking":
                self._latest_status = "说话中…"
                self._set_text_status("说话中", "#4a90e2")
                self._show_voice_status(self._latest_status, 0)
                self.input.setDisabled(True)
            elif v == "idle":
                self.input.setDisabled(False)
                self._recording = False
                self._stop_thinking()
                self._set_text_status("就绪", "#3aab6b")
                self._hide_voice_status_later()
                if self._ui_mode == "text":
                    self.input.setFocus()
        elif t == "transcript":
            content = ev.get("content", "")
            self._latest_status = f"你说：{content}"
            self._set_text_status("已转写", "#4a90e2")
            if content:
                self._add_message("user", content)
            self._show_voice_status(self._latest_status, 2500)
        elif t == "tool":
            name = ev.get("name")
            self._latest_status = f"正在调用 {name}…"
            self._set_text_status("工具中", "#e0982f")
            self._start_thinking(f"调用 {name}")
            self._show_voice_status(self._latest_status, 0)
        elif t == "reply":
            content = ev.get("content", "")
            self._latest_status = content
            self._set_text_status("已回复", "#3aab6b")
            self._stop_thinking()
            if content:
                self._add_message("bot", content)
            self._show_voice_status(self._latest_status, 4500)
        elif t == "error":
            self.orb.set_state("error")
            message = ev.get("message")
            self._latest_status = f"出错：{message}"
            self._set_text_status("出错", "#e74c3c")
            self._stop_thinking()
            self._add_message("error", f"出错：{message}")
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
        if not self._greeted:
            self._greeted = True
            self._add_message("bot", "你好，我是日历助手 👋\n有什么日程上的事都可以问我。")
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
        self._set_text_status("清除中", "#e0982f")
        self._stop_thinking()
        self._clear_messages()
        if self._ui_mode == "text":
            self._add_message("bot", "上下文已清除，我们重新开始吧～")
        self._show_voice_status(self._latest_status, 0)

    def _clear_messages(self) -> None:
        # 移除末尾 stretch 之外的所有消息行
        while self.msg_layout.count() > 1:
            item = self.msg_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _set_text_status(self, text: str, color: str = "#9aa3af") -> None:
        self.status_label.setText(f"● {text}")
        self.status_label.setStyleSheet(
            "QLabel { background: transparent; border: none;"
            f" color: {color}; font-size: 12px; font-weight: 500; }}"
        )

    # ===== chatbot 消息 =====
    def _make_bubble(self, role: str, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lbl.setMaximumWidth(BUBBLE_MAX_WIDTH)
        lbl.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Minimum)
        if role == "user":
            lbl.setStyleSheet(USER_BUBBLE_QSS)
        elif role == "error":
            lbl.setStyleSheet(ERROR_BUBBLE_QSS)
        else:
            lbl.setStyleSheet(BOT_BUBBLE_QSS)
        return lbl

    def _make_row(self, role: str, bubble: QWidget) -> QWidget:
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        if role == "user":
            h.addStretch(1)
            h.addWidget(bubble)
        else:
            h.addWidget(bubble)
            h.addStretch(1)
        return row

    def _add_message(self, role: str, text: str) -> QWidget:
        bubble = self._make_bubble(role, text)
        row = self._make_row(role, bubble)
        # 插在末尾 stretch 之前
        self.msg_layout.insertWidget(self.msg_layout.count() - 1, row)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return row

    def _scroll_to_bottom(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _start_thinking(self, base: str = "思考中") -> None:
        self._thinking_base = base
        if self._thinking_row is not None:
            self._thinking_label.setText(base)
        else:
            self._thinking_label = self._make_bubble("bot", base)
            self._thinking_row = self._make_row("bot", self._thinking_label)
            self.msg_layout.insertWidget(self.msg_layout.count() - 1, self._thinking_row)
            QTimer.singleShot(0, self._scroll_to_bottom)
        self._thinking_phase = 0
        if not self._thinking_timer.isActive():
            self._thinking_timer.start()

    def _tick_thinking(self) -> None:
        if self._thinking_label is None:
            self._thinking_timer.stop()
            return
        self._thinking_phase = (self._thinking_phase + 1) % 4
        self._thinking_label.setText(f"{self._thinking_base}{'·' * self._thinking_phase}")

    def _stop_thinking(self) -> None:
        self._thinking_timer.stop()
        if self._thinking_row is not None:
            self.msg_layout.removeWidget(self._thinking_row)
            self._thinking_row.deleteLater()
        self._thinking_row = None
        self._thinking_label = None

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
        if not text.startswith("/"):
            self._add_message("user", text)
        self._set_text_status("发送中", "#4a90e2")
        self.input.clear()

    def eventFilter(self, obj, event):
        if obj in {self.chat_header, self.title_label, self.status_label}:
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
