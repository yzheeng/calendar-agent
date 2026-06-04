# src/agent/loop.py
import json
import turtle

from src.agent.context import trim_messages
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


def run_agent(user_text: str, messages: list) -> tuple[str, list]:
    messages.append({"role": "user", "content": user_text})

    while True:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=trim_messages(messages, 20),
            tools=tools,
        )
        message = response.choices[0].message
        messages.append(message.model_dump())  ## messages返回全量历史
        if not message.tool_calls:
            return message.content, messages

        TOOL_REGISTRY = {
            "create_reminder": create_reminder,
            "list_reminders": list_reminders,
            "delete_reminder": delete_reminder,
            "update_reminder": update_reminder,
        }
        for tool_call in message.tool_calls:
            name = tool_call.function.name
            print(f"正在调用工具{name}")

            try:
                args = json.loads(tool_call.function.arguments)
                func = TOOL_REGISTRY.get(name)
                if func is None:
                    result = {"status": "fail", "message": f"未知工具：{name}"}
                else:
                    result = func(**args)
            except json.JSONDecodeError as e:
                result = {"status": "fail", "message": f"参数解析失败：{e}"}
            except Exception as e:
                result = {"status": "fail", "message": f"工具执行出错：{e}"}

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
