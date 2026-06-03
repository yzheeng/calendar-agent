from src.agent.run_agent import run_agent, new_session
from src.voice.record import record
from src.voice.transcribe import transcribe

EXIT_WORDS = ("退出", "再见", "结束", "拜拜")


def main():
    if __name__ == "__main__":
        ## 获取历史session对话记录
        messages = new_session()

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


if __name__ == "__main__":
    main()
