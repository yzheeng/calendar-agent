import json
from pathlib import Path

from src.agent.prompt import _system_message, SYSTEM_PROMPT

# 存储路径写死成模块级常量，save 和 load 共用同一处，杜绝路径不一致。
# parents[2] 从本文件(src/memory/session.py)往上三级，正好到项目根目录。
STORE_DIR = Path(__file__).resolve().parents[2] / "memory_store"
SESSION_FILE = STORE_DIR / "session.json"



def save_session(messages: list) -> str:
    print("正在将当前session写入磁盘")
    """把当前会话(messages)写入磁盘，返回写入的文件路径。"""
    STORE_DIR.mkdir(parents=True, exist_ok=True)  # 目录不存在就建，已存在也不报错
    with open(SESSION_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)  # ensure_ascii=False 让中文正常显示
    return str(SESSION_FILE)


def load_session() -> list:
    """读回上次的会话；文件不存在(第一次运行)就返回一段全新会话。"""
    if not SESSION_FILE.exists():
        return []
    with open(SESSION_FILE, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    save_session([{"role":"user","content":"测试中文"}])