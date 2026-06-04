from src.agent.context import assemble_context, strip_system
from src.agent.run_agent import run_agent
from src.memory.profile import update_profile
from src.memory.session import  save_session
from src.voice.record import record
from src.voice.transcribe import transcribe
from src.voice.tts import speak

EXIT_WORDS = ("退出", "再见", "结束", "拜拜")

def main():
    messages = assemble_context()

    while True:
        try:
            audio_path = record("audio/recording.wav")
            text = transcribe(audio_path)
        except Exception as e:
            print(f"录音或转写出错，跳过这轮：{e}")
            continue
        if not text:
            continue
        if any(w in text for w in EXIT_WORDS):
            print("助手已退出。")
            break
        print(f"用户输入内容：{text}")
        reply, messages = run_agent(text, messages)
        print(f"助手：{reply}")
        speak(reply)

    history = strip_system(messages)
    save_session(history)
    update_profile(history)


if __name__ == "__main__":
    main()
