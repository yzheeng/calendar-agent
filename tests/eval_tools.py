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
# due_offset_days:   期望日期相对"今天"偏移几天（None 表示不检查日期）
# title_contains:    期望 title 里应包含的关键词（None 表示不检查）
# reminder_id:       期望 reminder_id 等于该值（None 表示不检查）
# range_offset_days: 期望 list_reminders 的 (start_offset, end_offset)，按天数偏移今天
# expect_no_range:   期望 list_reminders 不带 start/end（保护向后兼容）
COMMON_CASES = [
    {"input": "提醒我明天下午3点开会",
     "expect_tool": "create_reminder", "title_contains": "开会", "due_offset_days": 1, "reminder_id": None},
    {"input": "帮我记一下后天上午十点跟王总开会",
     "expect_tool": "create_reminder", "title_contains": "王总", "due_offset_days": 2, "reminder_id": None},
    {"input": "我今天有哪些提醒事项？",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None, "reminder_id": None,
     "range_offset_days": (0, 0)},
    {"input": "把明天的开会提醒删掉",
     "expect_tool": "delete_reminder", "title_contains": None, "due_offset_days": None, "reminder_id": None},
    {"input": "今天都安排了什么",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None, "reminder_id": None,
     "range_offset_days": (0, 0)},
    {"input": "完成今天下午那个提醒",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None, "reminder_id": None,
     "range_offset_days": (0, 0)},
    {"input": "明天有什么安排",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None, "reminder_id": None,
     "range_offset_days": (1, 1)},
    {"input": "未来三天的提醒",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None, "reminder_id": None,
     "range_offset_days": (0, 3)},
    {"input": "列一下所有提醒",
     "expect_tool": "list_reminders", "title_contains": None, "due_offset_days": None, "reminder_id": None,
     "expect_no_range": True},
    {"input": "杭州明天天气怎么样？",
     "expect_tool": "web_search", "title_contains": None, "due_offset_days": None, "reminder_id": None},
    {"input": "今天美元对人民币多少？",
     "expect_tool": "web_search", "title_contains": None, "due_offset_days": None, "reminder_id": None},
]

# 模糊用例：表面像「问外部世界」、实际不该走 web_search。
# 用来观察模型加了联网工具之后会不会过度泛化。
AMBIGUOUS_NO_SEARCH_CASES = [
    {"input": "昨天是不是挺热的？", "expect_not_tool": "web_search"},
    {"input": "下周三是几号？", "expect_not_tool": "web_search"},
    {"input": "光速是多少？", "expect_not_tool": "web_search"},
    {"input": "我明天有什么安排？", "expect_not_tool": "web_search"},
    {"input": "你是谁啊？", "expect_not_tool": "web_search"},
]

NOISE_ONLY_CASES = [
    {"input": "把练腿标记完成了",
     "expect_tool": "complete_reminder", "title_contains": None, "due_offset_days": None,
     "reminder_id": "x-apple-reminder://" + "D" * 36},
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

    # 反例：只要求实际工具不等于 expect_not_tool（不调任何工具也算通过）
    if case.get("expect_not_tool"):
        if call is not None and call.function.name == case["expect_not_tool"]:
            return False, f"不该调 {case['expect_not_tool']}，但调了"
        return True, "通过"

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

    if case["reminder_id"]:
        reminder_id = args.get("reminder_id", "")
        if reminder_id != case["reminder_id"]:
            return False, f"reminder_id 不对：期望 {case['reminder_id']}，实际 reminder_id=「{reminder_id}」"

    if case.get("range_offset_days") is not None:
        s_off, e_off = case["range_offset_days"]
        s_date = (datetime.now() + timedelta(days=s_off)).strftime("%Y-%m-%d")
        e_date = (datetime.now() + timedelta(days=e_off)).strftime("%Y-%m-%d")
        start = args.get("start", "")
        end = args.get("end", "")
        if s_date not in start:
            return False, f"start 日期不对：期望含 {s_date}，实际 start=「{start}」"
        if e_date not in end:
            return False, f"end 日期不对：期望含 {e_date}，实际 end=「{end}」"

    if case.get("expect_no_range"):
        if args.get("start") or args.get("end"):
            return False, f"期望不传时间范围，实际 start=「{args.get('start','')}」end=「{args.get('end','')}」"

    return True, "通过"


def main():
    for label, noise, cases in [
        ("干净上下文", False, COMMON_CASES + AMBIGUOUS_NO_SEARCH_CASES),
        ("长噪声上下文", True, COMMON_CASES + NOISE_ONLY_CASES + AMBIGUOUS_NO_SEARCH_CASES),
    ]:
        passed = 0
        print(f"\n===== {label} =====")
        for i, case in enumerate(cases, 1):
            ok, reason = check_case(case, with_noise=noise)
            print(f"[{i}] {'✅' if ok else '❌'} {case['input']}" + (f"  ← {reason}" if not ok else ""))
            passed += ok
        print(f"通过率：{passed}/{len(cases)} = {passed / len(cases) * 100:.0f}%")


if __name__ == "__main__":
        main()
