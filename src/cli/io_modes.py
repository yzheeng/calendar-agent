from src.voice.record import record
from src.voice.transcribe import transcribe
from src.voice.tts import speak

AUDIO_PATH = "audio/recording.wav"

# 输入源 / 输出口的分发。按 state 里的模式决定走文本还是语音。

def get_input(state: dict) -> str:
    if state["input_mode"] == "voice":
        audio_path = record(AUDIO_PATH)
        text = transcribe(audio_path)
        text = text.encode("utf-8", "ignore").decode("utf-8")
        print(f"你说：{text}")
        return text
    return input("user> ").strip()


def deliver_output(text: str, state: dict) -> None:
    print(f"助手：{text}")
    if state["output_mode"] == "voice":
        speak(text)