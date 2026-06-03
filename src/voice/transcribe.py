import os
import uuid
import base64
import requests
from pathlib import Path
from dotenv import load_dotenv


load_dotenv()
app_id=os.getenv("APP_ID")
access_token=os.getenv("ACCESS_TOKEN")

RECOGNIZE_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/recognize/flash"


def transcribe(file_path: str) -> str:
    print("正在语音转文字")
    """
    把本地音频文件转成文字。
    成功返回识别出的文字；失败抛出异常，让调用方知道转写没成。
    """
    # 1. 读音频文件，转成 base64（火山要求音频以 base64 塞进请求体）
    with open(file_path, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")

    # 2. 组装请求头和请求体
    headers = {
        "X-Api-App-Key": app_id,
        "X-Api-Access-Key": access_token,
        "X-Api-Resource-Id": "volc.bigasr.auc_turbo",  # 极速版（flash）
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Sequence": "-1",
    }
    payload = {
        "user": {"uid": app_id},
        "audio": {"data": audio_base64},
        "request": {"model_name": "bigmodel"},
    }

    # 3. 发请求
    response = requests.post(RECOGNIZE_URL, json=payload, headers=headers)

    # 4. 检查状态码：20000000 才是成功
    status = response.headers.get("X-Api-Status-Code", "")
    if status != "20000000":
        message = response.headers.get("X-Api-Message", "未知错误")
        raise RuntimeError(f"语音识别失败 [{status}]: {message}")

    # 5. 从返回里取出完整文字
    text = response.json()["result"]["text"]
    return text


if __name__ == "__main__":
    from pathlib import Path
    audio = Path(__file__).resolve().parents[2] / "audio" / "recording.wav"
    print(transcribe(str(audio)))