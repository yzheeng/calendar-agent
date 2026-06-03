import subprocess

def create_reminder(title: str, due: str | None = None) -> dict:
    """
    往「提醒事项」加一条。
    due 格式示例: "2026-06-04 18:00"（可选）
    返回 dict，作为 tool_result 回传给模型。
    """
    if due:
        script = f'''
        tell application "Reminders"
            set newReminder to make new reminder with properties {{name:"{title}"}}
            set remind me date of newReminder to date "{due}"
        end tell
        '''
    else:
        script = f'''
        tell application "Reminders"
            make new reminder with properties {{name:"{title}"}}
        end tell
        '''

    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        return {"status": "fail", "message": f"创建失败：{e.stderr.strip()}"}

    when = f"，时间 {due}" if due else "（无指定时间）"
    return {"status": "success", "message": f"已创建提醒：{title}{when}"}

