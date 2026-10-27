"""Voice questions → text, for residents who can't read or type.

Two ways, tried in order:
1. GROQ_API_KEY set → Whisper large-v3 on Groq's free tier (`language="bn"`), which
   accepts Telegram's OGG/Opus voice notes as they are.
2. Otherwise the main model's audio input (Muse Spark lists audio understanding)
   via an OpenAI-style `input_audio` part — unverified shape; any failure means
   "no transcript" and the bot asks the user to type.
"""
import base64
import os

from .llm import _load_dotenv, get_llm

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
WHISPER_MODEL = "whisper-large-v3"

PROMPT = """This is a voice message to a flood-alert service in Dhaka, most likely in Bangla.
Transcribe exactly what the person asks, in the language they spoke (Bangla in Bangla script).
Reply with the transcript only, no commentary. If there is no intelligible speech, reply with an empty string."""


def _whisper(audio: bytes, fmt: str) -> str | None:
    from openai import OpenAI

    client = OpenAI(base_url=GROQ_BASE_URL, api_key=os.environ["GROQ_API_KEY"], timeout=60, max_retries=1)
    try:
        r = client.audio.transcriptions.create(
            model=WHISPER_MODEL, file=(f"voice.{fmt}", audio), language="bn", response_format="text",
        )
    except Exception as e:
        print(f"⚠ Whisper failed: {e}")
        return None
    text = (r if isinstance(r, str) else getattr(r, "text", "")).strip()
    return text or None


def transcribe(audio: bytes, fmt: str = "ogg") -> str | None:
    _load_dotenv()
    if os.environ.get("GROQ_API_KEY"):
        return _whisper(audio, fmt)
    llm = get_llm()
    if llm is None:
        return None
    try:
        msg = llm.chat([{"role": "user", "content": [
            {"type": "text", "text": PROMPT},
            {"type": "input_audio", "input_audio": {"data": base64.b64encode(audio).decode(), "format": fmt}},
        ]}])
    except Exception as e:
        print(f"⚠ audio model failed: {e}")
        return None
    text = (msg.content or "").strip().strip('"')
    return text or None
