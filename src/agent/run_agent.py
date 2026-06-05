import json
import os

from dotenv import load_dotenv
from src.agent.context import trim_messages
from src.tools.complete_reminder import complete_reminder
from src.tools.create_reminder import create_reminder
from src.tools.delete_reminder import delete_reminder
from src.tools.list_reminders import list_reminders
from src.tools.update_reminder import update_reminder
from src.agent.llm import client
from pathlib import Path

load_dotenv()
context_window = os.getenv("CONTEXT_WINDOW", default="20")

TOOLS_PATH = Path(__file__).resolve().parent.parent / "tools" / "tools.json"
with open(TOOLS_PATH, encoding="utf-8") as f:
    tools = json.load(f)

TOOL_REGISTRY = {
    "complete_reminder": complete_reminder,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
    "delete_reminder": delete_reminder,
    "update_reminder": update_reminder,
}


def execute_tool(name: str, args: dict) -> dict:
    """执行单个工具调用，返回结果 dict。任何执行异常都包成 fail 结果，
    保证不会把整个 agent 打崩。"""
    func = TOOL_REGISTRY.get(name)
    if func is None:
        return {"status": "fail", "message": f"未知工具：{name}"}
    try:
        return func(**args)
    except Exception as e:
        return {"status": "fail", "message": f"工具执行出错：{e}"}


def run_agent(user_text: str, messages: list) -> tuple[str, list]:
    messages.append({"role": "user", "content": user_text})

    while True:
        response = client.chat.completions.create(
            model="qwen-plus",
            messages=trim_messages(messages, int(context_window)),
            tools=tools,
        )
        message = response.choices[0].message
        messages.append(message.model_dump())  ## messages返回全量历史
        if not message.tool_calls:
            return message.content, messages

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            print(f"正在调用工具{name}")

            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                result = {"status": "fail", "message": f"参数解析失败：{e}"}
            else:
                result = execute_tool(name, args)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
