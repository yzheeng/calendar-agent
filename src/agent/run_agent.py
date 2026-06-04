# src/agent/loop.py
import json
import turtle

from src.agent.prompt import _system_message
from src.tools.create_reminder import create_reminder
from src.tools.delete_reminder import delete_reminder
from src.tools.list_reminders import list_reminders
from src.tools.update_reminder import update_reminder
from src.agent.llm import client
from pathlib import Path


TOOLS_PATH = Path(__file__).resolve().parent.parent / "tools" / "tools.json"
with open(TOOLS_PATH, encoding="utf-8") as f:
    tools = json.load(f)

def run_agent(user_text: str, messages : list) -> turtle:
    messages.append({"role": "user", "content": user_text})

    while True:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=messages,
            tools=tools,
        )
        message = response.choices[0].message
        messages.append(message.model_dump()) ## 转为字典存入
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


