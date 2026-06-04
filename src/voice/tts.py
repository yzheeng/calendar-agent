import asyncio
import copy
import json
import os
import queue
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Coroutine, TypeVar

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False

from src.voice.volc_protocols import (
    EventType,
    MsgType,
    finish_connection,
    finish_session,
    receive_message,
    start_connection,
    start_session,
    task_request,
    wait_for_event,
)


load_dotenv()

T = TypeVar("T")
DEFAULT_ENDPOINT = "wss://openspeech.bytedance.com/api/v3/tts/bidirection"
DEFAULT_SAMPLE_RATE = 24000
DEFAULT_SEND_INTERVAL = 0.005
TEXT_BOUNDARIES = set("。！？；，、,.!?;\n")


@dataclass(frozen=True)
class TTSConfig:
    app_id: str
    access_token: str
    voice_type: str
    resource_id: str
    endpoint: str = DEFAULT_ENDPOINT

    @classmethod
    def from_env(cls) -> "TTSConfig":
        app_id = os.getenv("APP_ID", "").strip()
        access_token = os.getenv("ACCESS_TOKEN", "").strip()
        voice_type = os.getenv("TTS_VOICE_TYPE", "").strip()
        endpoint = os.getenv("TTS_ENDPOINT", DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
        resource_id = os.getenv("TTS_RESOURCE_ID", "").strip()

        missing = []
        if not app_id:
            missing.append("APP_ID")
        if not access_token:
            missing.append("ACCESS_TOKEN")
        if not voice_type:
            missing.append("TTS_VOICE_TYPE")
        if missing:
            joined = ", ".join(missing)
            raise RuntimeError(f"缺少豆包 TTS 配置：{joined}。请在 .env 中配置后重试。")

        return cls(
            app_id=app_id,
            access_token=access_token,
            voice_type=voice_type,
            resource_id=resource_id or get_resource_id(voice_type),
            endpoint=endpoint,
        )


def synthesize(text: str) -> bytes:
    """Synthesize text into mp3 bytes."""
    _validate_text(text)
    return _run(_synthesize(text=text, encoding="mp3", sample_rate=DEFAULT_SAMPLE_RATE))


def synthesize_to_file(text: str, output_path: str | None = None) -> str:
    """Synthesize text into an audio file and return the file path."""
    _validate_text(text)
    audio = synthesize(text)
    path = _default_output_path("mp3") if output_path is None else Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return str(path)


def speak(text: str) -> None:
    """Synthesize text into pcm and play it through the default output device."""
    _validate_text(text)
    _run(_speak(text=text, sample_rate=DEFAULT_SAMPLE_RATE))


def get_resource_id(voice_type: str) -> str:
    if voice_type.startswith("S_"):
        return "volc.megatts.default"
    return "volc.service_type.10029"


async def _synthesize(text: str, encoding: str, sample_rate: int) -> bytes:
    _validate_text(text)
    audio = bytearray()

    async def on_audio(chunk: bytes) -> None:
        audio.extend(chunk)

    await _run_tts_session(
        text=text,
        encoding=encoding,
        sample_rate=sample_rate,
        on_audio=on_audio,
    )
    if not audio:
        raise RuntimeError("豆包 TTS 未返回音频数据。")
    return bytes(audio)


async def _speak(text: str, sample_rate: int) -> None:
    _validate_text(text)
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError("缺少 sounddevice，无法播放音频。") from exc

    with sd.RawOutputStream(
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        blocksize=0,
    ) as stream:

        async def on_audio(chunk: bytes) -> None:
            stream.write(chunk)

        await _run_tts_session(
            text=text,
            encoding="pcm",
            sample_rate=sample_rate,
            on_audio=on_audio,
        )


async def _run_tts_session(
    text: str,
    encoding: str,
    sample_rate: int,
    on_audio: Any,
) -> None:
    config = TTSConfig.from_env()
    websockets = _load_websockets()
    headers = {
        "X-Api-App-Key": config.app_id,
        "X-Api-Access-Key": config.access_token,
        "X-Api-Resource-Id": config.resource_id,
        "X-Api-Connect-Id": str(uuid.uuid4()),
    }

    websocket = await _connect(websockets, config.endpoint, headers)
    try:
        await start_connection(websocket)
        await wait_for_event(
            websocket,
            MsgType.FullServerResponse,
            EventType.ConnectionStarted,
        )

        session_id = str(uuid.uuid4())
        base_request = _base_request(
            voice_type=config.voice_type,
            encoding=encoding,
            sample_rate=sample_rate,
        )
        start_session_request = copy.deepcopy(base_request)
        start_session_request["event"] = EventType.StartSession

        await start_session(
            websocket,
            json.dumps(start_session_request, ensure_ascii=False).encode("utf-8"),
            session_id,
        )
        await wait_for_event(
            websocket,
            MsgType.FullServerResponse,
            EventType.SessionStarted,
        )

        send_task = asyncio.create_task(_send_text(websocket, session_id, base_request, text))
        try:
            await _receive_audio(websocket, on_audio)
        finally:
            await send_task
    finally:
        await _close_connection(websocket)


async def _send_text(websocket: Any, session_id: str, base_request: dict, text: str) -> None:
    for chunk in _iter_text_chunks(text):
        request = copy.deepcopy(base_request)
        request["event"] = EventType.TaskRequest
        request["req_params"]["text"] = chunk
        await task_request(
            websocket,
            json.dumps(request, ensure_ascii=False).encode("utf-8"),
            session_id,
        )
        await asyncio.sleep(DEFAULT_SEND_INTERVAL)

    await finish_session(websocket, session_id)


async def _receive_audio(websocket: Any, on_audio: Any) -> None:
    while True:
        msg = await receive_message(websocket)
        if msg.type == MsgType.AudioOnlyServer:
            if msg.payload:
                await on_audio(msg.payload)
            continue
        if msg.type == MsgType.Error:
            payload = msg.payload.decode("utf-8", "ignore")
            raise RuntimeError(f"豆包 TTS 失败 [{msg.error_code}]: {payload}")
        if msg.type != MsgType.FullServerResponse:
            raise RuntimeError(f"豆包 TTS 返回了未知消息：{msg}")
        if msg.event == EventType.SessionFinished:
            return
        if msg.event == EventType.SessionFailed:
            payload = msg.payload.decode("utf-8", "ignore")
            raise RuntimeError(f"豆包 TTS 会话失败：{payload}")
        if msg.event in {
            EventType.TTSSentenceStart,
            EventType.TTSSentenceEnd,
            EventType.TTSResponse,
            EventType.TTSEnded,
            EventType.UsageResponse,
        }:
            continue


async def _close_connection(websocket: Any) -> None:
    try:
        await finish_connection(websocket)
        await wait_for_event(
            websocket,
            MsgType.FullServerResponse,
            EventType.ConnectionFinished,
        )
    finally:
        await websocket.close()


async def _connect(websockets: Any, endpoint: str, headers: dict) -> Any:
    try:
        return await websockets.connect(
            endpoint,
            additional_headers=headers,
            max_size=10 * 1024 * 1024,
        )
    except TypeError as exc:
        if "additional_headers" not in str(exc):
            raise
        return await websockets.connect(
            endpoint,
            extra_headers=headers,
            max_size=10 * 1024 * 1024,
        )


def _base_request(voice_type: str, encoding: str, sample_rate: int) -> dict:
    return {
        "user": {"uid": str(uuid.uuid4())},
        "namespace": "BidirectionalTTS",
        "req_params": {
            "speaker": voice_type,
            "audio_params": {
                "format": encoding,
                "sample_rate": sample_rate,
                "enable_timestamp": False,
            },
            "additions": json.dumps(
                {
                    "disable_markdown_filter": False,
                },
                ensure_ascii=False,
            ),
        },
    }


def _iter_text_chunks(text: str, max_chars: int = 30) -> list[str]:
    chunks = []
    current = []
    for char in text:
        current.append(char)
        should_flush = char in TEXT_BOUNDARIES or len(current) >= max_chars
        if should_flush:
            chunk = "".join(current).strip()
            if chunk:
                chunks.append(chunk)
            current = []

    tail = "".join(current).strip()
    if tail:
        chunks.append(tail)
    return chunks


def _validate_text(text: str) -> None:
    if not isinstance(text, str):
        raise TypeError("text 必须是字符串。")
    if not text.strip():
        raise ValueError("text 不能为空。")


def _default_output_path(encoding: str) -> Path:
    root = Path(__file__).resolve().parents[2]
    filename = f"tts_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.{encoding}"
    return root / "audio" / filename


def _load_websockets() -> Any:
    try:
        import websockets
    except ImportError as exc:
        raise RuntimeError(
            "缺少 websockets 依赖，无法调用豆包双向 TTS。"
            "请在当前虚拟环境中安装：pip install 'websockets>=14.0'"
        ) from exc
    return websockets


def _run(coro: Coroutine[Any, Any, T]) -> T:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result_queue: queue.Queue[tuple[bool, Any]] = queue.Queue(maxsize=1)

    def runner() -> None:
        try:
            result_queue.put((True, asyncio.run(coro)))
        except Exception as exc:
            result_queue.put((False, exc))

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    ok, value = result_queue.get()
    if ok:
        return value
    raise value


if __name__ == "__main__":

    # audio_path = synthesize_to_file("好的，我已经帮你设置提醒了。")
    # print(audio_path)

    speak("日程已经安排好了")