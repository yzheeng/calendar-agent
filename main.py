import os

from dotenv import load_dotenv

from src.agent.llm import build_client
from src.config.settings import load_settings

load_dotenv()

from src.agent.context import assemble_context, strip_system
from src.agent.run_agent import run_agent
from src.memory.profile import update_profile
from src.memory.session import save_session
from src.cli.commands import is_command, handle_command
from src.cli.io_modes import get_input, deliver_output
from src.mcp.manager import MCPManager
from src.tools.local_tools import LOCAL_TOOL_DEFS

EXIT_WORDS = ("退出", "再见", "结束", "拜拜")


def main():
    messages = assemble_context()
    baseline_len = sum(1 for m in messages if m.get("role") != "system")
    settings = load_settings()
    client, model = build_client(settings)

    # 拉起 MCP server 并组装完整工具列表（MCP 动态发现 + 本地工具）
    mcp_manager = MCPManager(settings["mcpServers"])
    mcp_manager.start_all()
    tools = mcp_manager.openai_tools + LOCAL_TOOL_DEFS
    print(f"已加载 {len(mcp_manager.openai_tools)} 个 MCP 工具，{len(LOCAL_TOOL_DEFS)} 个本地工具。")

    # /tool 命令的展示快照：只投影名字，不让命令层接触 MCPManager 内部
    tool_summary = {
        "local": [t["function"]["name"] for t in LOCAL_TOOL_DEFS],
        "mcp": {},
    }
    for tool_name, client_obj in mcp_manager.tool_router.items():
        tool_summary["mcp"].setdefault(client_obj.name, []).append(tool_name)

    print(f"助手已启动（模型：{model}），输入 /help 看命令，/exit 退出。")

    state = {
        "client": client,
        "model": model,
        "settings": settings,
        "input_mode": settings["io"]["input_mode"],
        "output_mode": settings["io"]["output_mode"],
        "context_window": settings["agent"]["context_window"],
        "messages": messages,
        "baseline_len": baseline_len,
        "tool_summary": tool_summary,
    }

    # 主循环包进 try/finally，保证 MCP 子进程一定被回收
    try:
        while True:
            try:
                text = get_input(state)
            except (EOFError, KeyboardInterrupt):
                print()
                break
            except Exception as e:
                print(f"获取输入出错，跳过这轮：{e}")
                continue

            text = text.encode("utf-8", "ignore").decode("utf-8")
            if not text:
                continue
            if is_command(text):
                if handle_command(text, state) == "exit":
                    break
                continue
            if any(w in text for w in EXIT_WORDS):
                print("助手已退出。")
                break
            reply, state["messages"] = run_agent(
                text, state["messages"], state["client"], state["model"],
                state["context_window"], tools, mcp_manager,
            )
            deliver_output(reply, state)

        history = strip_system(state["messages"])
        save_session(history)
        new_messages = history[state["baseline_len"]:]
        update_profile(new_messages, state["client"], state["model"])
    finally:
        mcp_manager.close_all()


if __name__ == "__main__":
    main()