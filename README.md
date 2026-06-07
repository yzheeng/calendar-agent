# 语音驱动日程 Agent

一个跑在 macOS 上的语音驱动执行型 AI Agent：说一句话，它理解意图、编排日程，通过系统「提醒事项」真实写入并触发原生提醒。支持纯文本或纯语音两种交互方式，可在远程模型与本地模型间切换。

## 环境要求

- macOS
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) 包管理器

## 启动

```bash
# 1. 克隆并进入项目
git clone https://github.com/yzheeng/calendar-agent
cd calendarAgent

# 2. 安装依赖
uv sync

# 3. 配置环境变量, 在 .env 中填入对应api key
cp .env.example .env

# 4. 启动
uv run python main.py
```

> 首次运行时，macOS 会弹窗请求「自动化」（控制提醒事项）与「麦克风」权限，允许即可。

启动后直接打字对话，输入 `/help` 查看命令，`/voice` 切换全语音模式，`/exit` 退出。