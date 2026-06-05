import subprocess


def complete_reminder(reminder_id: str) -> dict:
    script = f'''
        tell application "Reminders"
            set theReminder to first reminder whose id is "{reminder_id}"
            set completed of theReminder to true
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
        return {"status": "fail", "message": f"标记完成失败：{e.stderr.strip()}"}

    return {"status": "success", "message": f"已完成：{reminder_id}"}


if __name__ == "__main__":
    complete_reminder("x-apple-reminder://E4E046E6-F85B-44B1-8A74-F02CDBB99206")
