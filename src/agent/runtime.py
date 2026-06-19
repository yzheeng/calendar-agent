import contextlib
import io
import threading
from dataclasses import dataclass
from typing import Callable

from dotenv import load_dotenv

from src.agent.approval import ask_tool_approval
from src.agent.context import assemble_context, strip_system
from src.agent.llm import build_client
from src.agent.run_agent import run_agent
from src.cli.commands import handle_command, is_command
from src.config.settings import load_settings
from src.mcp.manager import MCPManager
from src.memory.profile import update_profile
from src.memory.session import save_session
from src.tools.local_tools import LOCAL_TOOL_DEFS


EXIT_WORDS = ("退出", "再见", "结束", "拜拜")


@dataclass
class AgentResult:
    text: str
    should_exit: bool = False
    is_command: bool = False


class CalendarAgentRuntime:
    """Reusable Calendar Agent runtime for CLI and non-CLI entrypoints."""

    def __init__(
        self,
        approval_callback: Callable[[str, dict], bool] = ask_tool_approval,
        allow_interactive_commands: bool = True,
        event_callback: Callable[[dict], None] | None = None,
    ):
        self.approval_callback = approval_callback
        self.allow_interactive_commands = allow_interactive_commands
        self.event_callback = event_callback
        self.state: dict | None = None
        self.mcp_manager: MCPManager | None = None
        self.tools: list[dict] = []
        self.started = False
        self.closed = False
        self._lock = threading.RLock()

    def _emit(self, event: dict) -> None:
        if self.event_callback is not None:
            self.event_callback(event)

    def start(self) -> str:
        with self._lock:
            if self.started and not self.closed:
                return self.status_text()

            load_dotenv()
            messages = assemble_context()
            baseline_len = sum(1 for m in messages if m.get("role") != "system")
            settings = load_settings()
            client, model = build_client(settings)

            mcp_manager = MCPManager(settings["mcpServers"])
            mcp_manager.start_all()
            self.mcp_manager = mcp_manager
            self.tools = mcp_manager.openai_tools + LOCAL_TOOL_DEFS

            tool_summary = {
                "local": [t["function"]["name"] for t in LOCAL_TOOL_DEFS],
                "mcp": {},
            }
            for tool_name, client_obj in mcp_manager.tool_router.items():
                tool_summary["mcp"].setdefault(client_obj.name, []).append(tool_name)

            self.state = {
                "client": client,
                "model": model,
                "settings": settings,
                "input_mode": settings["io"]["input_mode"],
                "output_mode": settings["io"]["output_mode"],
                "context_window": settings["agent"]["context_window"],
                "require_tool_approval": settings["agent"]["require_tool_approval"],
                "messages": messages,
                "baseline_len": baseline_len,
                "tool_summary": tool_summary,
                "allow_interactive_commands": self.allow_interactive_commands,
            }
            self.started = True
            self.closed = False

            loaded = (
                f"已加载 {len(mcp_manager.openai_tools)} 个 MCP 工具，"
                f"{len(LOCAL_TOOL_DEFS)} 个本地工具。"
            )
            ready = f"助手已启动（模型：{model}），输入 /help 看命令，/exit 退出。"
            print(loaded)
            print(ready)
            return f"{loaded}\n{ready}"

    def status_text(self) -> str:
        with self._lock:
            if not self.state:
                return "助手尚未启动。"
            settings = self.state["settings"]
            tool_mode = "人工确认" if self.state.get("require_tool_approval") else "自动"
            return (
                f"当前模式：{settings['mode']}\n"
                f"当前模型：{self.state['model']}\n"
                f"输入：{self.state['input_mode']}   输出：{self.state['output_mode']}\n"
                f"工具执行：{tool_mode}"
            )

    def ask(self, text: str, capture_command_output: bool = True) -> AgentResult:
        with self._lock:
            self._ensure_started()
            assert self.state is not None
            assert self.mcp_manager is not None

            text = text.encode("utf-8", "ignore").decode("utf-8").strip()
            if not text:
                return AgentResult("")

            if is_command(text):
                output, should_exit = self._run_command(text, capture_command_output)
                if should_exit:
                    if not output:
                        output = "助手已退出。"
                    self.close()
                self._emit({"type": "reply", "content": output, "is_command": True})
                return AgentResult(output, should_exit=should_exit, is_command=True)

            if any(word in text for word in EXIT_WORDS):
                self.close()
                self._emit({"type": "reply", "content": "助手已退出。", "is_command": False})
                return AgentResult("助手已退出。", should_exit=True)

            self._emit({"type": "state", "value": "thinking"})
            reply, self.state["messages"] = run_agent(
                text,
                self.state["messages"],
                self.state["client"],
                self.state["model"],
                self.state["context_window"],
                self.tools,
                self.mcp_manager,
                self.state["require_tool_approval"],
                self.approval_callback,
                on_event=self.event_callback,
            )
            self._emit({"type": "reply", "content": reply or "", "is_command": False})
            self._emit({"type": "state", "value": "idle"})
            return AgentResult(reply or "")

    def close(self) -> None:
        with self._lock:
            if self.closed:
                return
            try:
                if self.state:
                    history = strip_system(self.state["messages"])
                    save_session(history)
                    new_messages = history[self.state["baseline_len"]:]
                    if new_messages:
                        try:
                            update_profile(
                                new_messages,
                                self.state["client"],
                                self.state["model"],
                            )
                        except Exception as exc:
                            print(f"提醒：整理用户偏好失败（{exc}），已跳过。")
            finally:
                if self.mcp_manager:
                    self.mcp_manager.close_all()
                self.closed = True
                self.started = False

    def _ensure_started(self) -> None:
        if not self.started or self.closed or not self.state or not self.mcp_manager:
            raise RuntimeError("Calendar Agent 尚未启动。")

    def _run_command(self, text: str, capture_output: bool) -> tuple[str, bool]:
        assert self.state is not None
        if capture_output:
            stream = io.StringIO()
            with contextlib.redirect_stdout(stream):
                result = handle_command(text, self.state)
            return stream.getvalue().strip(), result == "exit"
        result = handle_command(text, self.state)
        return "", result == "exit"
