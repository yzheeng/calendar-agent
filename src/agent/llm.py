from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(
    # 如果没有配置环境变量，请用阿里云百炼API Key替换：api_key="sk-xxx"
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# messages = [{"role": "user", "content": "你是谁"}]
# completion = client.chat.completions.create(
#     model="qwen-plus",  # 您可以按需更换为其它深度思考模型
#     messages=messages
# )
# print(completion.choices[0].message.content)


