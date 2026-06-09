## 行为层评测：通过模拟用户输入，验证模型是否能准确触发目标工具，并传入符合预期的参数。
from dotenv import load_dotenv
load_dotenv()
import json
from datetime import datetime, timedelta
from pathlib import Path

from src.agent.llm import build_client
from src.config.settings import load_settings
from src.agent.run_agent import tools
from src.agent.prompt import _system_message

# 评测专用 client, 从setting配置中构造
client, MODEL = build_client(load_settings())

DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "tool_selection.json"


def load_cases() -> list:
    with open(DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


# 一段结构合法但冗长的噪声历史，模拟真实长 session
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


def get_first_tool_call(user_text: str, with_noise: bool = False):
    # 喂一句输入给模型，返回它第一步发起的第一个 tool_call
    history = NOISE_HISTORY if with_noise else []
    messages = [_system_message()] + history + [{"role": "user", "content": user_text}]
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        tools=tools,
    )
    tool_calls = response.choices[0].message.tool_calls
    return tool_calls[0] if tool_calls else None


def check_case(case: dict, with_noise: bool = False) -> tuple[bool, str]:
    # 跑一条用例：拿 input 去问模型，再拿 expect 这一整包逐项核对。
    expect = case["expect"]
    call = get_first_tool_call(case["input"], with_noise=with_noise)

    # 验证: 绝对不调的工具
    if "not_tool" in expect:
        if call is not None and call.function.name == expect["not_tool"]:
            return False, f"不该调 {expect['not_tool']}，但调了"
        return True, "通过"

    # 验证: 必须调用的工具
    if call is None:
        return False, "没有调用任何工具"
    actual = call.function.name
    if actual != expect["tool"]:
        return False, f"工具名错：期望 {expect['tool']}，实际 {actual}"

    args = json.loads(call.function.arguments)

    if "title_contains" in expect:
        title = args.get("title", "")
        if expect["title_contains"] not in title:
            return False, f"title 不含「{expect['title_contains']}」，实际 title=「{title}」"

    if "due_offset_days" in expect:
        expected_date = (datetime.now() + timedelta(days=expect["due_offset_days"])).strftime("%Y-%m-%d")
        due = args.get("due", "")
        if expected_date not in due:
            return False, f"due 日期不对：期望含 {expected_date}，实际 due=「{due}」"

    if "reminder_id" in expect:
        rid = args.get("reminder_id", "")
        if rid != expect["reminder_id"]:
            return False, f"reminder_id 不对：期望 {expect['reminder_id']}，实际=「{rid}」"

    if "range_offset_days" in expect:
        s_off, e_off = expect["range_offset_days"]
        s_date = (datetime.now() + timedelta(days=s_off)).strftime("%Y-%m-%d")
        e_date = (datetime.now() + timedelta(days=e_off)).strftime("%Y-%m-%d")
        start, end = args.get("start", ""), args.get("end", "")
        if s_date not in start:
            return False, f"start 日期不对：期望含 {s_date}，实际 start=「{start}」"
        if e_date not in end:
            return False, f"end 日期不对：期望含 {e_date}，实际 end=「{end}」"

    if expect.get("expect_no_range"):
        if args.get("start") or args.get("end"):
            return False, f"期望不传范围，实际 start=「{args.get('start','')}」end=「{args.get('end','')}」"

    return True, "通过"


def main():
    cases = load_cases()
    ## 不含上下文噪声
    clean_cases = [c for c in cases if not c.get("requires_noise")]

    for label, with_noise, group in [
        ("干净上下文", False, clean_cases),
        ("长噪声上下文", True, cases),
    ]:
        passed = 0
        print(f"\n===== {label} =====")
        for i, case in enumerate(group, 1):
            ok, reason = check_case(case, with_noise=with_noise)
            print(f"[{i}] {'✅' if ok else '❌'} {case['input']}" + (f"  ← {reason}" if not ok else ""))
            passed += ok
        print(f"通过率：{passed}/{len(group)} = {passed / len(group) * 100:.0f}%")


if __name__ == "__main__":
    main()