"""读写 settings.json：存可公开的配置（模型名、base_url、模式），不存密钥。
密钥仍在 .env，由代码按约定去读。"""
import json
from pathlib import Path

# settings.json 放在项目根目录（这个文件在 src/config/ 下，往上两级就是根）
SETTINGS_PATH = Path(__file__).resolve().parents[2] / "settings.json"

# 一份完整的默认配置。文件不存在或残缺时，用它兜底。
DEFAULTS = {
    "mode": "remote",
    "remote": {
        "model": "qwen-plus",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    },
    "local": {
        "model": "",
        "base_url": "",
    },
}


def _merge(defaults: dict, override: dict) -> dict:
    """把 override 叠加到 defaults 上，缺的字段用 defaults 补。
    支持一层嵌套（remote / local 里的字段也能逐个补齐）。"""
    result = {}
    for key, default_value in defaults.items():
        if isinstance(default_value, dict):
            sub = override.get(key, {})
            sub = sub if isinstance(sub, dict) else {}
            result[key] = {**default_value, **sub}
        else:
            result[key] = override.get(key, default_value)
    return result


def load_settings() -> dict:
    """读 settings.json，返回完整配置。文件不存在或坏了，都回退到默认值。"""
    if not SETTINGS_PATH.exists():
        return _merge(DEFAULTS, {})          # 等于返回 DEFAULTS 的副本

    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"settings.json 读取失败（{e}），改用默认配置。")
        return _merge(DEFAULTS, {})

    if not isinstance(data, dict):
        print("settings.json 格式不对（不是对象），改用默认配置。")
        return _merge(DEFAULTS, {})

    return _merge(DEFAULTS, data)            


def save_settings(settings: dict) -> None:
    """把配置写回 settings.json。写之前先合并一遍，保证存进去的是完整结构。"""
    complete = _merge(DEFAULTS, settings)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(complete, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    s = load_settings()
    print(json.dumps(s, ensure_ascii=False, indent=2))