"""本地工具"""

LOCAL_TOOL_DEFS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索实时信息。当用户问到需要最新外部信息才能回答的问题"
                           "（天气、新闻、股价、汇率、比分、当前事件、某地某店营业状态等）时调用；"
                           "与提醒事项无关的实时类问题也走这里。"
                           "纯闲聊、常识题、日期推算、用户自己的提醒事项不要调。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "用于联网搜索的查询语句，尽量包含时间和地点等关键限定词，"
                                       "例如『杭州 明天 天气』。",
                    }
                },
                "required": ["query"],
            },
        },
    },
]