import json

from src.agent.context import assemble_context
from src.cli.io_modes import persist_io_modes
from src.cli.model_config import run_model_config
from src.config.settings import save_settings
from src.memory.profile import load_profile
from src.memory.session import clear_session

def _cmd_help(args, state):
    print("可用命令：")
    print("  /help            显示这个帮助")
    print("  /status          显示当前模型 / 输入输出模式")
    print("  /model_setting   进入模型配置")
    print("  /input <text|voice>    切换输入模式")
    print("  /output <text|voice>   切换输出模式")
    print("  /voice           一键全语音")
    print("  /text            一键全文本")
    print("  /profile         查看当前用户长期偏好")
    print("  /set_context <n> 设置上下文滑动窗口大小")
    print("  /clear_context   清空当前会话上下文")
    print("  /exit            退出助手")
    return "continue"


def _cmd_status(args, state):
    settings = state["settings"]
    print(f"当前模式：{settings['mode']}")
    print(f"当前模型：{state['model']}")
    print(f"输入：{state['input_mode']}   输出：{state['output_mode']}")
    return "continue"


def _cmd_exit(args, state):
    return "exit"

def _cmd_model_setting(args, state):
    run_model_config(state)
    return "continue"

_VALID_IO = ("text", "voice")


def _cmd_input(args, state):
    if not args or args[0] not in _VALID_IO:
        print(f"用法：/input text 或 /input voice（当前：{state['input_mode']}）")
        return "continue"
    state["input_mode"] = args[0]
    persist_io_modes(state)
    print(f"输入模式已切换为：{args[0]}")
    return "continue"


def _cmd_output(args, state):
    if not args or args[0] not in _VALID_IO:
        print(f"用法：/output text 或 /output voice（当前：{state['output_mode']}）")
        return "continue"
    state["output_mode"] = args[0]
    persist_io_modes(state)
    print(f"输出模式已切换为：{args[0]}")
    return "continue"


def _cmd_voice(args, state):
    state["input_mode"] = "voice"
    state["output_mode"] = "voice"
    persist_io_modes(state)
    print("已切换为全语音模式（输入+输出都是语音）。说「退出」可结束。")
    return "continue"


def _cmd_text(args, state):
    state["input_mode"] = "text"
    state["output_mode"] = "text"
    persist_io_modes(state)
    print("已切换为全文本模式（输入+输出都是文本）。")
    return "continue"


def _cmd_clear_context(args, state):
    clear_session()
    state["messages"] = assemble_context()
    state["baseline_len"] = 0
    print("已清空当前会话上下文。")
    return "continue"


def _cmd_profile(args, state):
    profile = load_profile()
    print(json.dumps(profile, ensure_ascii=False, indent=2))
    return "continue"


def _cmd_set_context(args, state):
    if not args or not args[0].isdigit():
        print(f"用法：/set_context <正整数>（当前：{state['context_window']}）")
        return "continue"
    n = int(args[0])
    if n < 2:
        print("窗口至少 2 条。")
        return "continue"
    state["context_window"] = n
    state["settings"]["agent"]["context_window"] = n
    try:
        save_settings(state["settings"])
    except OSError as e:
        print(f"提醒：保存窗口大小失败（{e}），仅本次会话生效。")
        return "continue"
    print(f"上下文窗口已设为 {n}。下一轮对话生效。")
    return "continue"


_REGISTRY = {
    "help": _cmd_help,
    "status": _cmd_status,
    "exit": _cmd_exit,
    "model_setting": _cmd_model_setting,
    "input": _cmd_input,
    "output": _cmd_output,
    "voice": _cmd_voice,
    "text": _cmd_text,
    "profile": _cmd_profile,
    "set_context": _cmd_set_context,
    "clear_context": _cmd_clear_context,
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