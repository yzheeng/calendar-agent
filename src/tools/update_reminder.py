import subprocess

def update_reminder(reminder_id : str, new_title: str | None = None, new_due: str | None = None ) -> dict:
    script = f'''
    tell application "Reminders"
        set theReminder to first reminder whose id is "{reminder_id}"
    '''
    if new_title:
        script += f'set name of theReminder to "{new_title}"\n'
    if new_due:  # 注意：if 不是 elif
        script += f'set remind me date of theReminder to date "{new_due}"\n'

    script += 'end tell'

    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        print(e.stderr)
        return {"status": "fail", "message": f"更新失败：{e.stderr.strip()}"}

    return {"status": "success", "message": f"更新成功：{reminder_id}"}


if __name__ == "__main__":
    print(update_reminder("x-apple-reminder://E4E046E6-F85B-44B1-8A74-F02CDBB99206", new_title="剪发"))