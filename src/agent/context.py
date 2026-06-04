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