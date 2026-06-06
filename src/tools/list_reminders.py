import subprocess
from datetime import datetime


_DUE_FMT = "%Y-%m-%d %H:%M:%S"
_ARG_FMT = "%Y-%m-%d %H:%M"


def list_reminders(
    start: str | None = None,
    end: str | None = None,
    include_undated: bool = False,
) -> dict:
    script = '''
            tell application "Reminders"
                set output to ""
                repeat with r in (every reminder in default list whose completed is false)
                    set rid to id of r
                    set rtitle to name of r
                    set rdue to ""
                    set d to remind me date of r
                    if d is not missing value then
                        set y to year of d as integer
                        set mo to month of d as integer
                        set dd to day of d as integer
                        set hh to hours of d as integer
                        set mi to minutes of d as integer
                        set se to seconds of d as integer
                        set rdue to (text -4 thru -1 of ("0000" & y)) & "-" & ¬
                                    (text -2 thru -1 of ("00" & mo)) & "-" & ¬
                                    (text -2 thru -1 of ("00" & dd)) & " " & ¬
                                    (text -2 thru -1 of ("00" & hh)) & ":" & ¬
                                    (text -2 thru -1 of ("00" & mi)) & ":" & ¬
                                    (text -2 thru -1 of ("00" & se))
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

    if start is None and end is None:
        return {"status": "success", "reminders": reminders}

    try:
        start_dt = datetime.strptime(start, _ARG_FMT) if start else None
        end_dt = datetime.strptime(end, _ARG_FMT) if end else None
    except ValueError:
        return {"status": "fail", "message": "时间格式不对，应为 YYYY-MM-DD HH:MM"}

    filtered = []
    for r in reminders:
        due = r["due"]
        if not due:
            if include_undated:
                filtered.append(r)
            continue
        try:
            due_dt = datetime.strptime(due, _DUE_FMT)
        except ValueError:
            continue
        if start_dt and due_dt < start_dt:
            continue
        if end_dt and due_dt > end_dt:
            continue
        filtered.append(r)

    return {"status": "success", "reminders": filtered}


if __name__ == "__main__":
    list_reminders()
