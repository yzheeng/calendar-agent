from src.config.settings import save_settings
from src.voice.record import record
from src.voice.transcribe import transcribe
from src.voice.tts import speak

AUDIO_PATH = "audio/recording.wav"

# 输入源 / 输出口的分发。按 state 里的模式决定走文本还是语音。

def get_input(state: dict) -> str:
    if state["input_mode"] == "voice":
        line = input("[回车录音 / 输入 /命令] > ").strip()
        if line.startswith("/"):
            return line
        if line:
            print("语音模式下仅接受 / 开头的命令；其它请说出来。")
            return ""
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


def persist_io_modes(state: dict) -> None:
    """把当前 input/output 模式写回 settings.json，下次启动可直接加载。"""
    state["settings"]["io"] = {
        "input_mode": state["input_mode"],
        "output_mode": state["output_mode"],
    }
    try:
        save_settings(state["settings"])
    except OSError as e:
        print(f"提醒：保存 IO 模式失败（{e}），仅本次会话生效。")