import json


APPROVE_WORDS = {"y", "yes", "是", "确认", "允许", "同意", "好", "可以"}


def is_approved_answer(text: str) -> bool:
    """用确定性规则判断用户是否批准本次工具调用。"""
    return text.strip().lower() in APPROVE_WORDS


def ask_tool_approval(tool_name: str, args: dict) -> bool:
    """在工具真正执行前请求用户确认。默认拒绝。"""
    print("\n即将调用工具：")
    print(f"  名称：{tool_name}")
    print("  参数：")
    print(json.dumps(args, ensure_ascii=False, indent=2))
    try:
        answer = input("是否允许执行？[y/N] > ")
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return is_approved_answer(answer)
