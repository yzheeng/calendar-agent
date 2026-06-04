from datetime import datetime

SYSTEM_PROMPT = (
    "你是一个跑在 macOS 上的语音日程助手。用户用自然语言安排日程，"
    "你理解意图并调用工具读写「提醒事项」。回复要简短、口语化，适合朗读出来。"
)


def _system_message() -> dict:
    now = datetime.now().strftime("%Y-%m-%d %H:%M %A")  # 例: 2026-06-03 14:30 Tuesday
    return {
        "role": "system",
        "content": f"{SYSTEM_PROMPT}\n当前时间是 {now}，据此推算"
                   f"用户提到的相对时间（如：明天、下周一）。",
    }