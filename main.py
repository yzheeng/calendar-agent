from src.agent.runtime import CalendarAgentRuntime
from src.cli.io_modes import get_input, deliver_output


def main():
    runtime = CalendarAgentRuntime()
    runtime.start()

    try:
        while True:
            try:
                text = get_input(runtime.state)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            except Exception as e:
                print(f"获取输入出错，跳过这轮：{e}")
                continue

            result = runtime.ask(text, capture_command_output=False)
            if result.should_exit:
                if result.text:
                    print(result.text)
                break
            if result.is_command:
                continue
            deliver_output(result.text, runtime.state)
    finally:
        runtime.close()


if __name__ == "__main__":
    main()
