import json
from pathlib import Path

STORE_DIR = Path(__file__).resolve().parents[2] / "memory_store"
PROFILE_FILE = STORE_DIR / "profile.json"

EMPTY_PROFILE = {"preferences": [], "facts": [], "routines": []}

MERGE_SYSTEM_PROMPT = """
你是一个用户偏好提炼器。你会收到「已有的用户档案」和「本次对话」。
你的任务：从对话中提炼出值得**长期记住**的稳定信息，与已有档案合并，输出合并后的完整档案。

输出必须是严格的 JSON，包含且仅包含这三个字段：
- preferences: 主观偏好（最多 8 条）
- facts: 客观稳定信息（最多 8 条）
- routines: 周期性规律（最多 8 条）

【绝对不要记录】出现以下特征的内容，必须丢弃，不要写进档案：
1. 含具体日期 / 月份 / 具体某一天的内容
   ❌ "用户计划 6月8日起每日查看 XX"  → 这是一次性安排
   ❌ "本周五要寄快递"                → 临时事件
2. 工具调用结果里的具体提醒标题 / 任务名 / 日程条目原文
   ❌ "用户周日要研究 Langfuse / 读 MLflow 的 Judge Alignment" → 这是 reminder 数据，不是用户偏好
3. 一次性闲谈、单次问答
   ❌ "用户问过淄博天气"
4. 与系统 / 助手自身有关的元信息
   ❌ "用户使用私人语音助手"
   ❌ "用户希望助手保持务实风格"（对助手风格的临时要求不算长期偏好）

【应当记录】跨时间稳定、与具体某一天无关的内容：
✅ "用户偏好晚上锻炼"           → 跨时间稳定的主观偏好
✅ "用户使用 macOS"             → 客观长期事实
✅ "用户每周五安排练腿"          → 周期性规律（不绑定到某一周）

合并规则：
1. 新信息与旧档案冲突时，保留新的、丢弃旧的（例：旧"晚上锻炼"、新"改到早上" → 留早上）。
2. 相似条目主动合并为一条更概括的，避免重复。
3. 每个分类硬性上限 8 条；如果合并后会超额，删除最旧或最具体 / 信号最弱的一条。
4. 只输出 JSON 本身，不要任何解释、不要 Markdown 代码块、不要寒暄。
"""


def load_profile() -> dict:
    """读用户长期档案；不存在或读坏了都回退到空档案。"""
    if not PROFILE_FILE.exists():
        return dict(EMPTY_PROFILE)
    try:
        with open(PROFILE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return dict(EMPTY_PROFILE)


def _sanitize_for_combine(messages: list) -> list:
    """combine 前的清洗：只保留 user / assistant 的文本 content。
    丢掉 tool 消息、assistant 的 tool_calls 那种空 content 的消息、reasoning_content
    等噪声 —— 它们会污染 profile（把提醒标题当 routine、把 CoT 当 fact）。"""
    cleaned = []
    for m in messages:
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if not content or not isinstance(content, str):
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def combine_profile(messages: list, client, model: str) -> dict:
    """把本次会话 merge 进 profile。"""
    cleaned = _sanitize_for_combine(messages)
    profile = load_profile()
    # 清洗后没料就别花 LLM 调用了
    if not cleaned:
        return profile

    print("正在整理用户最新偏好")
    profile_text = json.dumps(profile, ensure_ascii=False)
    dialogue_text = json.dumps(cleaned, ensure_ascii=False)
    merge_messages = [
        {"role": "system", "content": MERGE_SYSTEM_PROMPT},
        {"role": "user", "content": f"已有档案：\n{profile_text}\n\n本次对话：\n{dialogue_text}"},
    ]
    response = client.chat.completions.create(
        model=model,
        messages=merge_messages,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return profile


def save_profile(profile: dict) -> str:
    print("正在保存用户最新偏好")
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return str(PROFILE_FILE)


def update_profile(messages: list, client, model: str) -> str:
    return save_profile(combine_profile(messages, client, model))
