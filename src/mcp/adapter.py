"""adapter.py（适配层）：只做格式翻译"""

def mcp_tool_to_openai(tool: dict) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool.get("description", ""),
            "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
        },
    }


def mcp_tools_to_openai(tools: list[dict]) -> list[dict]:
    return [mcp_tool_to_openai(t) for t in tools]