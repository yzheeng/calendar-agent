import json
import subprocess


class MCPClient:

    PROTOCOL_VERSION = "2025-03-26"

    def __init__(self, name: str, command: list[str]):
        self.name = name          # server 的名字，如 "reminders"
        self.command = command    # 启动命令，如 ["uv", "--directory", "/path", "run", "apple-reminders-mcp-server"]
        self.process = None
        self._id = 0              # JSON-RPC 请求 id 计数器

    # ---------- 生命周期 ----------

    def start(self) -> None:
        """拉起 server 子进程并完成握手。"""
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
            bufsize=1,
        )
        self._request("initialize", {
            "protocolVersion": self.PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "calendar-agent", "version": "0.1"},
        })
        self._notify("notifications/initialized")

    def close(self) -> None:
        """关闭管道并终止子进程。"""
        if self.process is None:
            return
        try:
            self.process.stdin.close()
            self.process.terminate()
            self.process.wait(timeout=3)
        except Exception:
            self.process.kill()

    # ---------- 协议原语 ----------

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    def _send(self, msg: dict) -> None:
        line = json.dumps(msg, ensure_ascii=False)
        self.process.stdin.write(line + "\n")
        self.process.stdin.flush()

    def _notify(self, method: str, params: dict | None = None) -> None:
        msg = {"jsonrpc": "2.0", "method": method}
        if params:
            msg["params"] = params
        self._send(msg)

    def _request(self, method: str, params: dict | None = None) -> dict:
        """发请求并阻塞等待对应 id 的响应。"""
        msg_id = self._next_id()
        msg = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params:
            msg["params"] = params
        self._send(msg)

        # 循环读，跳过通知等无关消息，直到等到自己 id 的响应
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError(f"MCP server「{self.name}」进程已退出")
            data = json.loads(line)
            if data.get("id") != msg_id:
                continue
            if "error" in data:
                raise RuntimeError(f"MCP 错误 [{self.name}]: {data['error']}")
            return data["result"]

    # ---------- 业务接口 ----------

    def list_tools(self) -> list[dict]:
        """工具发现"""
        return self._request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict) -> dict:
        """调用工具"""
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        text = result["content"][0]["text"]
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"status": "success", "raw": text}


if __name__ == "__main__":
    client = MCPClient(
        name="reminders",
        command=["uv", "--directory", "/Users/yzheng/PycharmProjects/reminder-mcp-server",
                 "run", "apple-reminders-mcp-server"],
    )
    client.start()
    print("已连接，工具清单：")
    for t in client.list_tools():
        print(" -", t["name"])
    print(client.call_tool("list_reminders", {}))
    client.close()