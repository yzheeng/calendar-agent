from pathlib import Path
import json

STORE_DIR = Path(__file__).resolve().parents[2] / "memory_store"
PROFILE_FILE = STORE_DIR / "profile.json"

EMPTY_PROFILE = {"preferences": [], "facts": [], "routines": []}

MERGE_SYSTEM_PROMPT = """
你是一个用户偏好提炼器。你会收到「已有的用户档案」和「本次对话内容」。
你的任务：从本次对话中提炼出值得长期记住的稳定信息，与已有档案合并，输出合并后的完整档案。

输出必须是严格的 JSON，包含且仅包含这三个字段：
- preferences: 主观偏好（如"锻炼习惯排在晚上"）
- facts: 客观稳定信息（如"周会习惯叫站会"）
- routines: 周期性规律（如"每周一有读书任务"）

规则：
1. 只记录跨会话长期有用的信息；一次性的具体日程（如"明天3点开会"）不要记录。
2. 新信息优先于旧信息：若新旧冲突（如旧档案"锻炼排晚上"、本次说"改到早上"），保留新的、丢弃旧的。
3. 不要存重复的条目。
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


def combine_profile(messages : list, client, model:str) -> dict:
    print("正在整理用户最新偏好")
    profile = load_profile()
    # 1. 把素材都转成字符串（content 只收字符串，不收 dict）
    profile_text = json.dumps(profile, ensure_ascii=False)
    dialogue_text = json.dumps(messages, ensure_ascii=False)
    # 2. 新建一个干净的临时消息列表，system 在前、user 在后
    merge_messages = [
        {"role": "system", "content": MERGE_SYSTEM_PROMPT},
        {"role": "user", "content": f"已有档案：\n{profile_text}\n\n本次对话：\n{dialogue_text}"},
    ]
    response = client.chat.completions.create(
        model=model,
        messages=merge_messages,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content  # 要的是这段文本，不是整条消息

    # 3. 解析成 dict；万一解析失败，退回旧 profile（这次没学到，保持原样）
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return profile

def save_profile(profile: dict) -> str:
    print("正在保存用户最新偏好")
    """把档案写回磁盘，返回文件路径。"""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    return str(PROFILE_FILE)


def update_profile(messages : list, client, model:str) -> str:
    return save_profile(combine_profile(messages, client, model))

