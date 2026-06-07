import sounddevice as sd
from scipy.io.wavfile import write
from pathlib import Path

SAMPLE_RATE = 16000  # 采样率 16kHz，语音识别的常用值


# def record(output_path: str) -> str:
#     """
#     回车开始录音，再按回车停止。把录音存成 wav 文件，返回文件路径。
#     """
#     input("按回车开始录音...")
#     print("录音中... 再次按回车停止")
#
#     # 开始录音：先开一段足够长的缓冲（最多录 60 秒），靠回车提前打断
#     recording = sd.rec(int(60 * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1)
#     input()           # 卡在这等你按回车
#     sd.stop()         # 停止录音
#
#     # 存成 wav 文件
#     write(output_path, SAMPLE_RATE, recording)
#     print(f"录音已保存：{output_path}")
#     return output_path


import sounddevice as sd
import numpy as np
from scipy.io.wavfile import write

def record(output_path: str) -> str:
    """开始录音，按回车停止。把录音存成 wav 文件，返回文件路径。"""
    print("录音中... 再次按回车停止")

    frames = []

    def callback(indata, frame_count, time_info, status):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, callback=callback):
        input()

    if not frames:
        recording = np.zeros((1, 1), dtype="float32")
    else:
        recording = np.concatenate(frames, axis=0)

    write(output_path, SAMPLE_RATE, recording)
    print(f"录音已保存：{output_path}")
    return output_path

if __name__ == "__main__":
    input("按回车开始录音...")
    audio = Path(__file__).resolve().parents[2] / "audio" / "recording.wav"
    record(str(audio))