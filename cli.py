from dotenv import load_dotenv

load_dotenv()

from src.agent.context import assemble_context, strip_system
from src.agent.run_agent import run_agent
from src.memory.profile import update_profile
from src.memory.session import save_session
from src.cli.commands import is_command, handle_command  # 新增

EXIT_WORDS = ("退出", "再见", "结束", "拜拜")


def main():
    messages = assemble_context()
    state = {}
    print("助手已启动，直接打字对话（输入 /help 看命令，/exit 退出）。")

    while True:
        try:
            text = input("user> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        # 清洗字符串
        text = text.encode("utf-8", "ignore").decode("utf-8")
        # 空输入
        if not text:
            continue
        # 处理命令
        if is_command(text):
            if handle_command(text, state) == "exit":
                break
            continue

        if any(w in text for w in EXIT_WORDS):
            print("助手已退出。")
            break

        reply, messages = run_agent(text, messages)
        print(f"助手：{reply}")

    history = strip_system(messages)
    save_session(history)
    update_profile(history)


if __name__ == "__main__":
    main()
