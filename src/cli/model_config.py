"""模型配置界面：进入后引导用户选 remote/local 并填写对应配置。
这个文件只管“模型配置怎么交互”，不管顶层命令分发。"""
from src.agent.llm import build_client
from src.config.settings import save_settings


def _ask(prompt: str, current: str) -> str:
    """问一个配置项。显示当前值，回车保留，否则用新值。"""
    shown = current if current else "（空）"
    raw = input(f"{prompt}\n  当前：{shown}\n  直接回车保留，或输入新值 > ").strip()
    return current if raw == "" else raw


def _configure_one(settings: dict, mode: str) -> None:
    """引导填写某一类（remote / local）的字段，原地改 settings。"""
    conf = settings[mode]

    if mode == "remote":
        conf["model"] = _ask("远程模型名（例如 qwen-plus / qwen-max）", conf["model"])
        conf["base_url"] = _ask("远程 base_url", conf["base_url"])
        print("提示：远程密钥读取 .env 里的 DASHSCOPE_API_KEY，这里不填。")
    else:  # local
        print("提示：请确保本地服务（如 Ollama）已启动，且已 ollama pull 该模型。")
        conf["model"] = _ask("本地模型名（你 ollama 拉下来的那个）", conf["model"])
        conf["base_url"] = _ask("本地 base_url", conf["base_url"])


def run_model_config(state: dict) -> None:
    """模型配置的子循环。走完整个引导流程后返回，调用方继续主循环。"""
    settings = state["settings"]
    print("\n=== 模型配置 ===")
    print("选择模型来源：/remote 或 /local（/back 返回，不改任何东西）")

    while True:
        choice = input("设置> ").strip().lower()

        if choice in ("/back", "back"):
            print("已退出配置，未改动。\n")
            return

        if choice in ("/remote", "remote", "/local", "local"):
            mode = "remote" if "remote" in choice else "local"

            _configure_one(settings, mode)

            apply = input(f"是否立即切换到 {mode} 模型使用？(y/n) > ").strip().lower()
            if apply == "y":
                trial = dict(settings)
                trial["mode"] = mode
                try:
                    client, model = build_client(trial)
                except Exception as e:
                    print(f"启用失败，配置已记录但未切换：{e}")
                else:
                    settings["mode"] = mode
                    state["client"] = client
                    state["model"] = model
                    print(f"已切换到 {mode} 模型：{model}")

            save_settings(settings)
            print("配置已保存。\n")
            return

        print("请输入 /remote、/local 或 /back。")