# src/agent/loop.py
import json
import turtle
from datetime import datetime

from src.tools.create_reminder import create_reminder
from src.tools.delete_reminder import delete_reminder
from src.tools.list_reminders import list_reminders
from src.tools.update_reminder import update_reminder
from src.agent.llm import client
from datetime import datetime
from pathlib import Path


TOOLS_PATH = Path(__file__).resolve().parent.parent / "tools" / "tools.json"
with open(TOOLS_PATH, encoding="utf-8") as f:
    tools = json.load(f)

SYSTEM_PROMPT = (
    "你是一个跑在 macOS 上的语音日程助手。用户用自然语言安排日程，"
    "你理解意图并调用工具读写「提醒事项」。回复要简短、口语化，适合朗读出来。"
)


def _system_message() -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M %A")  # 例: 2026-06-03 14:30 Tuesday
    return {
        "role": "system",
        "content": f"{SYSTEM_PROMPT}\n当前时间是 {now}，据此推算"
                   f"用户提到的相对时间（如：明天、下周一）。",
    }

def new_session() -> list:
    """
    开一段新会话，返回初始 messages。
    这个 list 就是"工作上下文"——由调用方(main.py)持有，在多轮之间复用，
    从而保留会话内记忆。下一步我们会把它存到磁盘，实现跨进程的记忆。
    """
    return [_system_message()]



def run_agent(user_text: str, messages : list) -> turtle:

    messages[0] = _system_message();
    messages.append({"role": "user", "content": user_text})

    while True:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            tools=tools,
        )
        message = response.choices[0].message
        messages.append(message)
        ## 循环执行
        if not message.tool_calls:
            return message.content, messages

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)  # arguments 是 JSON 字符串
            print(f"正在调用工具{name}")

            if name == "create_reminder":
                result = create_reminder(**args)
            elif name == "list_reminders":
                result = list_reminders()
            elif name == "delete_reminder":
                result = delete_reminder(**args)
            elif name == "update_reminder":
                result = update_reminder(**args)
            else:
                result = {"status": "fail", "message": f"未知工具：{name}"}

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })



if __name__ == "__main__":
    session = new_session()
    reply, session = run_agent("提醒我明天下午3点开会", session)
    print("助手：", reply)
    reply, session = run_agent("把它改到4点", session)  # 依赖上一轮的记忆
    print("助手：", reply)