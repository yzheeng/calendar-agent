import asyncio
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.agent.runtime import CalendarAgentRuntime


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


bus = EventBus()
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
            if msg.get("type") == "text":
                asyncio.create_task(_handle_text(msg.get("content", "")))
    except WebSocketDisconnect:
        pass
    finally:
        sender_task.cancel()
        bus.detach()


async def _handle_text(content: str) -> None:
    try:
        await asyncio.to_thread(runtime.ask, content)
    except Exception as e:
        bus.emit({"type": "error", "message": str(e)})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="info")
