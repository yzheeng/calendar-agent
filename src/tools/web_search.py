import os
from tavily import TavilyClient



# 复用同一个 client，别每次调用都重建
_client = None
def _get_client() -> TavilyClient:
    global _client
    if _client is None:
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 TAVILY_API_KEY，去 .env 里填一下")
        _client = TavilyClient(api_key=api_key)
    return _client


def web_search(query: str) -> dict:
    """联网搜索实时信息。返回 Tavily 综合出的简短答案 + 几条来源摘要，
    交给模型据此口语化总结。任何异常都包成 fail，不让 agent 崩。"""
    try:
        resp = _get_client().search(
            query=query,
            search_depth="basic",   # basic 快且省；要更全可改 advanced
            max_results=3,          # 喂给模型的条数，别太多免得撑爆上下文
            include_answer=True,    # 让 Tavily 先综合出一句答案，最适合朗读
        )
    except Exception as e:
        return {"status": "fail", "message": f"搜索失败：{e}"}

    # 每条来源的正文截断一下，保持上下文精简
    results = [
        {
            "title": r.get("title", ""),
            "content": (r.get("content", "") or "")[:300],
        }
        for r in resp.get("results", [])
    ]
    return {
        "status": "success",
        "answer": resp.get("answer", ""),
        "results": results,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print(web_search("杭州明天天气怎么样"))




