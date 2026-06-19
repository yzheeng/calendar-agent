import asyncio
import threading
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.agent.runtime import CalendarAgentRuntime
from src.voice.record import record_until_stopped
from src.voice.transcribe import transcribe
from src.voice.tts import speak


AUDIO_PATH = str(Path(__file__).resolve().parent / "audio" / "ws_recording.wav")


class EventBus:
    """Bridge worker-thread events into the asyncio loop. Single-client assumption."""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._queue: asyncio.Queue | None = None

    def attach(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        self._loop = loop
        self._queue = queue

    def detach(self) -> None:
        self._loop = None
        self._queue = None

    def emit(self, event: dict) -> None:
        loop, queue = self._loop, self._queue
        if loop is None or queue is None:
            return
        loop.call_soon_threadsafe(queue.put_nowait, event)


class VoiceSession:
    """单客户端假设下的语音会话状态。"""

    def __init__(self):
        self.recording = False
        self.stop_event: threading.Event | None = None
        self.record_thread: threading.Thread | None = None
        self.result: dict[str, str] = {}

    def reset(self):
        self.recording = False
        self.stop_event = None
        self.record_thread = None
        self.result.clear()


bus = EventBus()
voice = VoiceSession()
runtime = CalendarAgentRuntime(
    # TODO: 后续阶段把工具确认改成 WS 往返；本期统一自动通过。
    approval_callback=lambda name, args: True,
    allow_interactive_commands=False,
    event_callback=bus.emit,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    runtime.start()
    try:
        yield
    finally:
        runtime.close()


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()
    bus.attach(loop, queue)

    await ws.send_json({
        "type": "ready",
        "model": runtime.state["model"],
        "tools_loaded": len(runtime.tools),
    })

    async def sender():
        while True:
            event = await queue.get()
            await ws.send_json(event)

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            msg = await ws.receive_json()
            t = msg.get("type")
            if t == "text":
                asyncio.create_task(_handle_text(msg.get("content", "")))
            elif t == "voice_start":
                asyncio.create_task(_handle_voice_start())
            elif t == "voice_stop":
                asyncio.create_task(_handle_voice_stop())
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        bus.detach()
        # 断线时若正在录音，触发停止以免线程僵死
        if voice.recording and voice.stop_event is not None:
            voice.stop_event.set()
            if voice.record_thread is not None:
                voice.record_thread.join(timeout=2)
        voice.reset()


async def _handle_text(content: str) -> None:
    try:
        await asyncio.to_thread(runtime.ask, content)
    except Exception as e:
        bus.emit({"type": "error", "message": str(e)})


async def _handle_voice_start() -> None:
    if voice.recording:
        return
    voice.recording = True
    voice.stop_event = threading.Event()
    voice.result.clear()
    bus.emit({"type": "state", "value": "listening"})

    stop_event = voice.stop_event

    def _record():
        try:
            voice.result["path"] = record_until_stopped(AUDIO_PATH, stop_event)
        except Exception as e:
            voice.result["error"] = str(e)

    voice.record_thread = threading.Thread(target=_record, daemon=True)
    voice.record_thread.start()


async def _handle_voice_stop() -> None:
    if not voice.recording or voice.stop_event is None:
        return
    voice.stop_event.set()
    if voice.record_thread is not None:
        await asyncio.to_thread(voice.record_thread.join, 5)
    voice.recording = False

    if "error" in voice.result:
        err = voice.result.pop("error")
        voice.result.clear()
        bus.emit({"type": "error", "message": f"录音失败: {err}"})
        bus.emit({"type": "state", "value": "idle"})
        return

    path = voice.result.pop("path", None)
    voice.result.clear()
    if path is None:
        bus.emit({"type": "error", "message": "录音线程未返回文件路径。"})
        bus.emit({"type": "state", "value": "idle"})
        return

    try:
        text = (await asyncio.to_thread(transcribe, path)).strip()
    except Exception as e:
        bus.emit({"type": "error", "message": f"语音识别失败: {e}"})
        bus.emit({"type": "state", "value": "idle"})
        return

    if not text:
        bus.emit({"type": "error", "message": "没听清，再说一次？"})
        bus.emit({"type": "state", "value": "idle"})
        return

    bus.emit({"type": "transcript", "content": text})

    try:
        result = await asyncio.to_thread(runtime.ask, text, True, False)
    except Exception as e:
        bus.emit({"type": "error", "message": str(e)})
        bus.emit({"type": "state", "value": "idle"})
        return

    reply = (result.text or "").strip()
    if reply:
        bus.emit({"type": "state", "value": "speaking"})
        try:
            await asyncio.to_thread(speak, reply)
        except Exception as e:
            bus.emit({"type": "error", "message": f"朗读失败: {e}"})
    bus.emit({"type": "state", "value": "idle"})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
