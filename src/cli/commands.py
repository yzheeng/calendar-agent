from src.cli.model_config import run_model_config

def _cmd_help(args, state):
    print("可用命令：")
    print("  /help           显示这个帮助")
    print("  /status         显示当前模型 / 模式")
    print("  /model_setting  进入模型配置（选 remote/local 并填写）")
    print("  /exit           退出助手")
    return "continue"


def _cmd_status(args, state):
    settings = state["settings"]
    print(f"当前模式：{settings['mode']}")
    print(f"当前模型：{state['model']}")
    return "continue"


def _cmd_exit(args, state):
    return "exit"

def _cmd_model_setting(args, state):
    run_model_config(state)
    return "continue"

_REGISTRY = {
    "help": _cmd_help,
    "status": _cmd_status,
    "exit": _cmd_exit,
    "model_setting": _cmd_model_setting,
}


def is_command(text: str) -> bool:
    return text.startswith("/")


def handle_command(text: str, state: dict) -> str:
    """处理一条 slash 命令，返回 'continue' 或 'exit'。
    state 是个共享字典，后面用来放模型、I/O 模式等。这步先不用它。"""
    parts = text[1:].split()          # 去掉开头的 /，按空格切
    if not parts:
        print("空命令。输入 /help 看看有哪些命令。")
        return "continue"

    name, args = parts[0], parts[1:]
    func = _REGISTRY.get(name)
    if func is None:
        print(f"未知命令：/{name}。输入 /help 看看有哪些命令。")
        return "continue"

    return func(args, state)