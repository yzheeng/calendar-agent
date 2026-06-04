import json

from src.agent.prompt import _system_message
from src.memory.profile import load_profile
from src.memory.session import load_session


def assemble_context() -> list:
    """装配喂给模型的完整上下文：现造的 system 消息 + 偏好+ load 回来的历史session。"""
    profile = load_profile()
    msg = _system_message()
    if profile:
        msg["content"] += (
            f"\n\n以下是该用户的长期偏好，安排时请参考：\n"
            f"{json.dumps(profile, ensure_ascii=False)}"
        )
    return [msg] + load_session()


def strip_system(messages: list) -> list:
    """从完整上下文里剥掉 system，只留对话轮次（存盘前用）。"""
    return [m for m in messages if m.get("role") != "system"]


def trim_messages(messages: list, max_messages: int) -> list:
    """喂给模型前裁剪上下文：永远保留 system，只留最近 max_messages 条历史，
    且不切断 assistant(tool_calls) 与其 tool 结果的配对。"""
    if not messages:
        return messages

    # 1. system 单独拎出来（约定它在第 0 位），它不占窗口名额
    system = messages[0] if messages[0].get("role") == "system" else None
    history = messages[1:] if system else messages

    # 2. 历史没超就原样返回，别瞎截
    if len(history) <= max_messages:
        return messages

    # 3. 从尾部取最近的 max_messages 条
    window = history[-max_messages:]

    # 4. 若开头是 tool（说明它对应的 assistant 被切走了），往后丢，
    #    直到开头不再是孤儿 tool 消息
    while window and window[0].get("role") == "tool":
        window = window[1:]

    # 5. system 放回最前
    return ([system] + window) if system else window
