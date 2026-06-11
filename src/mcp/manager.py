"""
manager.py（编排层）：读配置 → 批量拉起 client → 汇总工具
"""

from src.mcp.adapter import mcp_tools_to_openai
from src.mcp.mcp_client import MCPClient


class MCPManager:

    def __init__(self, mcp_config: dict):
        """mcp_config 即 settings["mcpServers"]，形如 {name: {command, args}}。"""
        self.clients: dict[str, MCPClient] = {}
        self.tool_router: dict[str, MCPClient] = {}
        self.openai_tools: list[dict] = []
        self._config = mcp_config

    def start_all(self) -> None:
        for name, conf in self._config.items():
            try:
                client = MCPClient(
                    name=name,
                    command=[conf["command"], *conf["args"]],
                )
                client.start()
                raw_tools = client.list_tools()
            except Exception as e:
                print(f"MCP server「{name}」启动失败，已跳过：{e}")
                continue

            self.clients[name] = client

            for tool in raw_tools:
                tool_name = tool["name"]
                # 重名策略：先到先得，后注册的跳过并警告。
                # 多 server 重名时，工业做法是加前缀（如 reminders__list_reminders），
                # 真遇到了再升级。
                if tool_name in self.tool_router:
                    print(f"工具重名「{tool_name}」（来自 {name}），已跳过后者。")
                    continue
                self.tool_router[tool_name] = client

            self.openai_tools.extend(
                mcp_tools_to_openai(
                    [t for t in raw_tools if self.tool_router.get(t["name"]) is client]
                )
            )

    def has_tool(self, name: str) -> bool:
        return name in self.tool_router

    def call_tool(self, name: str, args: dict) -> dict:
        """按路由表转发调用。任何异常都包成 fail dict，不向上抛。"""
        client = self.tool_router.get(name)
        if client is None:
            return {"status": "fail", "message": f"未知 MCP 工具：{name}"}
        try:
            return client.call_tool(name, args)
        except Exception as e:
            return {"status": "fail", "message": f"MCP 工具「{name}」执行出错：{e}"}

    def close_all(self) -> None:
        """逐个关闭，单个失败不影响其他。"""
        for name, client in self.clients.items():
            try:
                client.close()
            except Exception as e:
                print(f"关闭 MCP server「{name}」出错：{e}")
        self.clients.clear()
        self.tool_router.clear()
        self.openai_tools.clear()


if __name__ == "__main__":
    from src.config.settings import load_settings

    manager = MCPManager(load_settings()["mcpServers"])
    manager.start_all()
    print("已发现工具：", list(manager.tool_router.keys()))
    print(manager.call_tool("list_reminders", {}))
    print(manager.call_tool("不存在的工具", {}))   # 应返回 fail dict，而不是抛异常
    manager.close_all()
    print("已全部关闭。")