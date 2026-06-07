import json
import os


from src.agent.context import trim_messages
from src.tools.complete_reminder import complete_reminder
from src.tools.create_reminder import create_reminder
from src.tools.delete_reminder import delete_reminder
from src.tools.list_reminders import list_reminders
from src.tools.update_reminder import update_reminder
from src.tools.web_search import web_search
from pathlib import Path

context_window = int(os.getenv("CONTEXT_WINDOW", default="20"))
max_steps = int(os.getenv("MAX_STEPS", default="5"))

TOOLS_PATH = Path(__file__).resolve().parent.parent / "tools" / "tools.json"
with open(TOOLS_PATH, encoding="utf-8") as f:
    tools = json.load(f)

TOOL_REGISTRY = {
    "complete_reminder": complete_reminder,
    "create_reminder": create_reminder,
    "list_reminders": list_reminders,
    "delete_reminder": delete_reminder,
    "update_reminder": update_reminder,
    "web_search": web_search,
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


def run_agent(user_text: str, messages: list, client, model: str) -> tuple[str, list]:
    user_index = len(messages)  # 当前用户对话开启的位置
    messages.append({"role": "user", "content": user_text})

    for _ in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            messages=trim_messages(messages, context_window),
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
    # 兜底机制: 如果模型陷入了调用循环，无法停止。在达到max_step时，砍掉混乱的调用历史 只保留用户输入
    del messages[user_index + 1:]
    return "我这会儿有点忙,你待会儿再说一遍", messages