import json
import os
from typing import Callable


from src.agent.approval import ask_tool_approval
from src.agent.context import trim_messages
from src.tools.web_search import web_search

LOCAL_TOOLS = {
    "web_search": web_search,
}


def _max_steps() -> int:
    try:
        return int(os.getenv("MAX_STEPS", default="5"))
    except ValueError:
        return 5

def execute_tool(name: str, args: dict, mcp_manager) -> dict:
    """工具派发：本地工具直接调，其余交给 MCP manager 路由。"""
    func = LOCAL_TOOLS.get(name)
    if func is not None:
        try:
            return func(**args)
        except Exception as e:
            return {"status": "fail", "message": f"工具执行出错：{e}"}
    # 不在本地表里的，统一视为 MCP 工具；
    return mcp_manager.call_tool(name, args)


def run_agent(user_text: str, messages: list, client, model: str,
              context_window: int, tools: list, mcp_manager,
              require_tool_approval: bool = False,
              approval_callback=ask_tool_approval,
              on_event: Callable[[dict], None] | None = None) -> tuple[str, list]:
    user_index = len(messages)
    messages.append({"role": "user", "content": user_text})

    for _ in range(_max_steps()):
        response = client.chat.completions.create(
            model=model,
            messages=trim_messages(messages, context_window),
            tools=tools,
        )
        message = response.choices[0].message
        messages.append(message.model_dump())  # messages 返回全量历史
        if not message.tool_calls:
            return message.content, messages

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            if on_event is not None:
                on_event({"type": "tool", "name": name, "phase": "start"})

            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError as e:
                result = {"status": "fail", "message": f"参数解析失败：{e}"}
            else:
                if require_tool_approval and not approval_callback(name, args):
                    result = {
                        "status": "fail",
                        "message": "用户拒绝了本次工具调用，工具没有执行。",
                    }
                else:
                    result = execute_tool(name, args, mcp_manager)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(result, ensure_ascii=False),
            })
    # 兜底机制: 如果模型陷入了调用循环，达到 max_steps 时砍掉混乱的调用历史，只保留用户输入
    del messages[user_index + 1:]
    return "我这会儿有点忙,你待会儿再说一遍", messages
