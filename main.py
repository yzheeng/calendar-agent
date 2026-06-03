from src.agent.run_agent import run_agent
from src.voice.record import record
from src.voice.transcribe import transcribe

if __name__ == "__main__":
    output_path = record("audio/recording.wav")
    text = transcribe(output_path)
    result = run_agent(text)
    print(result)

