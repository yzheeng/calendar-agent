"""行为层评测：喂一句用户输入，检查模型第一步是否调对了工具、参数对不对。
不真正执行工具（无副作用），只看模型的调用决策。
运行：python -m tests.eval_tools
"""
import json
from datetime import datetime, timedelta

from src.agent.llm import client
from src.agent.run_agent import tools
from src.agent.prompt import _system_message


# 一段结构合法但冗长的噪声历史，模拟真实长 session：
# 多轮闲聊 + 一次完整的查询（assistant 带 tool_calls + 配对的 tool 结果，不留孤儿）
NOISE_HISTORY = [
    {"role": "user", "content": "今天天气怎么样？"},
    {"role": "assistant", "content": "我只管提醒事项，天气帮不上忙哦。"},
    {"role": "user", "content": "我今天有哪些提醒事项？"},
    {"role": "assistant", "content": "",
     "tool_calls": [{"id": "call_noise_1", "type": "function",
                     "function": {"name": "list_reminders", "arguments": "{}"}}]},
    {"role": "tool", "tool_call_id": "call_noise_1",
     "content": json.dumps({"status": "success", "reminders": [
         {"id": "x-apple-reminder://" + "A" * 36, "title": "阅读", "due": "2026年6月5日 星期五 00:00:00"},
         {"id": "x-apple-reminder://" + "B" * 36, "title": "快递", "due": "2026年6月5日 星期五 00:00:00"},
         {"id": "x-apple-reminder://" + "C" * 36, "title": "继续开发项目", "due": "2026年6月5日 星期五 10:30:00"},
         {"id": "x-apple-reminder://" + "D" * 36, "title": "练腿", "due": "2026年6月5日 星期五 15:30:00"},
     ]}, ensure_ascii=False)},
    {"role": "assistant", "content": "今天四件事：阅读、快递、上午十点半开发项目、下午三点半练腿。"},
    {"role": "user", "content": "好的知道了，谢谢。"},
    {"role": "assistant", "content": "不客气。"},
]


def get_first_tool_call_with_noise(user_text: str):
    """和 get_first_tool_call 一样，但在 system 和当前输入之间塞入噪声历史，
    模拟长 session。唯一的变量就是这段噪声。"""
    messages = [_system_message()] + NOISE_HISTORY + [{"role": "user", "content": user_text}]
    response = client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=tools,
    )
    tool_calls = response.choices[0].message.tool_calls
    return tool_calls[0] if tool_calls else None


# 每条用例：用户说的话 + 期望工具名 + 期望参数特征
# due_offset_days: 期望日期相对"今天"偏移几天（None 表示不检查日期）
# title_contains:  期望 title 里应包含的关键词（None 表示不检查）
CASES = [
    {"input": "提醒我明天下午3点开会",
     "expect_tool": "create_reminder", "title_contains": "开会", "due_offset_days": 1},
    {"input": "帮我记一下后天上午十点跟王总开会",
     "expect_tool": "create_reminder", "title_contains": "王总", "due_offset_days": 2},
    {"input": "我今天有哪些提醒事项？",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None},
    {"input": "把明天的开会提醒删掉",
     "expect_tool": "delete_reminder", "title_contains": None, "due_offset_days": None},
    {"input": "今天都安排了什么",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None},
]


def get_first_tool_call(user_text: str):
    """喂一句输入给模型，返回它第一步发起的第一个 tool_call；没调工具则返回 None。"""
    messages = [_system_message(), {"role": "user", "content": user_text}]
    response = client.chat.completions.create(
        model="qwen-plus",
        messages=messages,
        tools=tools,
    )
    tool_calls = response.choices[0].message.tool_calls
    return tool_calls[0] if tool_calls else None


def check_case(case: dict, with_noise: bool = False) -> tuple[bool, str]:
    call = (get_first_tool_call_with_noise if with_noise else get_first_tool_call)(case["input"])

    if call is None:
        return False, "没有调用任何工具"

    actual_tool = call.function.name
    if actual_tool != case["expect_tool"]:
        return False, f"工具名错：期望 {case['expect_tool']}，实际 {actual_tool}"

    args = json.loads(call.function.arguments)

    # 宽松匹配 title：包含即可
    if case["title_contains"]:
        title = args.get("title", "")
        if case["title_contains"] not in title:
            return False, f"title 不含「{case['title_contains']}」，实际 title=「{title}」"

    # 宽松匹配 due：动态算出期望日期，只比日期不比时分
    if case["due_offset_days"] is not None:
        expected_date = (datetime.now() + timedelta(days=case["due_offset_days"])).strftime("%Y-%m-%d")
        due = args.get("due", "")
        if expected_date not in due:
            return False, f"due 日期不对：期望含 {expected_date}，实际 due=「{due}」"

    return True, "通过"


def main():
    for label, noise in [("干净上下文", False), ("长噪声上下文", True)]:
        passed = 0
        print(f"\n===== {label} =====")
        for i, case in enumerate(CASES, 1):
            ok, reason = check_case(case, with_noise=noise)
            print(f"[{i}] {'✅' if ok else '❌'} {case['input']}" + (f"  ← {reason}" if not ok else ""))
            passed += ok
        print(f"通过率：{passed}/{len(CASES)} = {passed / len(CASES) * 100:.0f}%")


if __name__ == "__main__":
    main()