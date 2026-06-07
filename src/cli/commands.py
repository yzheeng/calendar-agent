
def _cmd_help(args, state):
    print("可用命令：")
    print("  /help    显示这个帮助")
    print("  /status  显示当前状态")
    print("  /exit    退出助手")
    return "continue"


def _cmd_status(args, state):
    print("当前状态：（暂无，后面会显示模型 / 输入输出模式）")
    return "continue"


def _cmd_exit(args, state):
    return "exit"


_REGISTRY = {
    "help": _cmd_help,
    "status": _cmd_status,
    "exit": _cmd_exit,
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