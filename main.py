from src.agent.run_agent import run_agent, new_session
from src.memory.profile import combine_profile, load_profile, save_profile
from src.memory.session import load_session, save_session
from src.voice.record import record
from src.voice.transcribe import transcribe

EXIT_WORDS = ("退出", "再见", "结束", "拜拜")


def main():
    profile = load_profile()
    messages = new_session(profile)

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

    save_session(messages)
    save_profile(combine_profile(messages, profile))


if __name__ == "__main__":
    main()
