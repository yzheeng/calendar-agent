import os

from dotenv import load_dotenv

from src.agent.llm import build_client
from src.config.settings import load_settings

load_dotenv()

from src.agent.context import assemble_context, strip_system
from src.agent.run_agent import run_agent
from src.memory.profile import update_profile
from src.memory.session import save_session
from src.cli.commands import is_command, handle_command
from src.cli.io_modes import get_input, deliver_output

EXIT_WORDS = ("退出", "再见", "结束", "拜拜")


def main():
    messages = assemble_context()
    # 加载默认llm设定
    settings = load_settings()
    client, model = build_client(settings)
    print(f"助手已启动（模型：{model}），输入 /help 看命令，/exit 退出。")

    # 全局状态 用于记录 client 和 model
    state = {
        "client": client,
        "model": model,
        "settings": settings,
        "input_mode": settings["io"]["input_mode"],
        "output_mode": settings["io"]["output_mode"],
        "messages": messages,
    }

    while True:
        try:
            text = get_input(state)
        except (EOFError, KeyboardInterrupt):
            print()
            break
        except Exception as e:
            print(f"获取输入出错，跳过这轮：{e}")
            continue
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
        # 退出判断
        if any(w in text for w in EXIT_WORDS):
            print("助手已退出。")
            break
        # 调用模型
        reply, state["messages"] = run_agent(text, state["messages"], state["client"], state["model"])
        deliver_output(reply, state)

    history = strip_system(state["messages"])
    save_session(history)
    update_profile(history, state["client"], state["model"])


if __name__ == "__main__":
    main()
