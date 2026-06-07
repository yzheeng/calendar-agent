import os
from openai import OpenAI


def build_client(settings: dict) -> tuple[OpenAI, str]:
    """按传入的配置造 client，返回 (client, model)。
    配置（model / base_url）来自 settings.json；密钥按约定从 .env 读。"""
    mode = settings.get("mode", "remote")

    if mode == "local":
        conf = settings["local"]
        model = conf.get("model", "")
        if not model:
            raise RuntimeError(
                "未配置本地模型名。请在 /model_setting 里填上你的模型名。"
            )
        client = OpenAI(api_key="local", base_url=conf["base_url"])
        return client, model

    if mode == "remote":
        conf = settings["remote"]
        api_key = os.getenv("DASHSCOPE_API_KEY")
        if not api_key:
            raise RuntimeError("未配置 DASHSCOPE_API_KEY，去 .env 里填一下。")
        client = OpenAI(api_key=api_key, base_url=conf["base_url"])
        return client, conf["model"]

    raise ValueError(f"未知的 mode：{mode}（只支持 remote / local）")
