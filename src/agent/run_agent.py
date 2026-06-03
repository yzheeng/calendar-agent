# src/agent/loop.py
import json
from datetime import datetime

from src.tools.delete_reminder import delete_reminder
from src.tools.list_reminders import list_reminders
from src.tools.update_reminder import update_reminder
from .llm import client
from ..tools.create_reminder import create_reminder
from datetime import datetime

# 读工具 schema
with open("src/tools/tools.json") as f:
    tools = json.load(f)


def run_agent(user_text: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M %A")  # 例: 2026-06-02 14:30 Monday
    messages = [{"role": "system", "content": f"当前的时间是 {now}。请根据它来推算用户提到的相对时间（如：明天、下周一）"},
                {"role": "user", "content": user_text},]

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
            return message.content

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
        # for 结束，不手动再调模型，while 转下一圈会把结果带给模型



if __name__ == "__main__": print(run_agent("提醒我明天下午3点开会"))