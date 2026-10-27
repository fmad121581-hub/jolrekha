"""LLM client — any OpenAI-compatible endpoint: Meta Model API (Muse Spark) or local Ollama (Llama).

Configured from a .env file or the environment:
    MODEL_API_KEY            API key (any non-empty value for local Ollama)
    JOLREKHA_LLM_BASE_URL    default https://api.meta.ai/v1; Ollama: http://localhost:11434/v1
    JOLREKHA_LLM_MODEL       default muse-spark-1.1; Ollama: e.g. llama3.1:8b
    JOLREKHA_VISION_MODEL    optional separate model for photos (e.g. llama3.2-vision:11b)
    JOLREKHA_LLM_TIMEOUT     seconds per request (default 60; local models need more)
    JOLREKHA_LLM_JSON_MODE   1 = ask the server for strict JSON (response_format), if it supports it
    JOLREKHA_LLM_REPLY_LANGS languages the model may write user-facing text in (default bn,en)

Without a key get_llm() returns None and the rest of the code falls back to
templates/rules.
"""
import json
import os
import re
from dataclasses import dataclass

from . import config

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_MODEL = "muse-spark-1.1"


def _load_dotenv(path=config.ROOT / ".env") -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class LLM:
    client: object
    model: str
    vision_model: str | None = None
    json_mode: bool = False

    def chat(self, messages, tools=None, model=None, **kw):
        args = {"model": model or self.model, "messages": messages, **kw}
        if tools:
            args["tools"] = tools
        return self.client.chat.completions.create(**args).choices[0].message

    def json(self, messages, **kw):
        """Parse JSON out of the reply — tolerates ```json fences and text around the object."""
        if self.json_mode:
            kw.setdefault("response_format", {"type": "json_object"})
        text = self.chat(messages, **kw).content or ""
        m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if m:
            text = m.group(1)
        elif not text.lstrip().startswith(("{", "[")):
            start = text.find("{")
            text = text[start:text.rfind("}") + 1] if start >= 0 else text
        return json.loads(text)


def reply_langs() -> set[str]:
    """Languages the model may write replies in (JOLREKHA_LLM_REPLY_LANGS, default "bn,en").

    Small local models write poor Bangla, so for them set "en": Bangla answers are then
    built from vetted templates while the model still decides *what* is being asked.
    """
    return {x.strip() for x in os.environ.get("JOLREKHA_LLM_REPLY_LANGS", "bn,en").split(",") if x.strip()}


_cached: LLM | None = None
_tried = False


def get_llm() -> LLM | None:
    global _cached, _tried
    if _tried:
        return _cached
    _tried = True
    _load_dotenv()
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        return None
    from openai import OpenAI

    client = OpenAI(
        base_url=os.environ.get("JOLREKHA_LLM_BASE_URL", DEFAULT_BASE_URL),
        api_key=key,
        timeout=float(os.environ.get("JOLREKHA_LLM_TIMEOUT", 60)),
        max_retries=2,
    )
    _cached = LLM(
        client,
        os.environ.get("JOLREKHA_LLM_MODEL", DEFAULT_MODEL),
        vision_model=os.environ.get("JOLREKHA_VISION_MODEL") or None,
        json_mode=os.environ.get("JOLREKHA_LLM_JSON_MODE") == "1",
    )
    return _cached
