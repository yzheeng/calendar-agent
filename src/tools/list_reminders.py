import subprocess

def list_reminders() -> dict:
    script = '''
            tell application "Reminders"
                set output to ""
                repeat with r in (every reminder in default list whose completed is false)
                    set rid to id of r
                    set rtitle to name of r
                    set rdue to ""
                    if (remind me date of r) is not missing value then
                        set rdue to (remind me date of r) as string
                    end if
                    set output to output & rid & "|" & rtitle & "|" & rdue & linefeed
                end repeat
                return output
            end tell
            '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
        raw = result.stdout

    except subprocess.CalledProcessError as e:
        return {"status": "fail", "message": f"拉取失败：{e.stderr}"}

    reminders = []
    for line in raw.strip().split("\n"):  # 按换行拆成每一行
        if not line:  # 跳过空行（末尾那个 linefeed 会产生空行）
            continue
        parts = line.split("|")  # 每行按 | 拆成 [id, 标题, 时间]
        reminders.append({
            "id": parts[0],
            "title": parts[1],
            "due": parts[2] if len(parts) > 2 else "",
        })

    return {"status": "success", "reminders": reminders}

if __name__ == "__main__":
    list_reminders()