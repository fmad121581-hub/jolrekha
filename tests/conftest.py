"""Shared fixtures: a tiny replay run on disk, a fake model, and isolated data files."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jolrekha import config  # noqa: E402

T0 = pd.Timestamp("2024-05-26 18:00")


class FakeMessage(SimpleNamespace):
    pass


def tool_call(name, args, id_="c1"):
    return SimpleNamespace(id=id_, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


class FakeLLM:
    """Replays canned replies; records what it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def chat(self, messages, tools=None, **kw):
        self.seen.append([dict(m) for m in messages])
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def json(self, messages, **kw):
        return json.loads(self.chat(messages).content)


def reply(content):
    return FakeMessage(content=content, tool_calls=None)


@pytest.fixture
def replay_run(tmp_path, monkeypatch):
    """outputs/replay_test/scores.csv with two Mohammadpur wards over 4 hours.

    Ward A goes yellow → red; ward B stays green. Returns (run_name, [A, B]).
    """
    from jolrekha.places import find_wards

    ids = find_wards("মোহাম্মদপুর")[:2]
    rows = []
    for h in range(4):
        for wid, lv, sc in [(ids[0], "red" if h >= 2 else "yellow", 0.3 + 0.2 * h), (ids[1], "green", 0.05)]:
            rows.append({"ward_id": wid, "name_bn": f"নাম-{wid[-4:]}", "name_en": f"Name-{wid[-4:]}",
                         "as_of": T0 + pd.Timedelta(hours=h), "score": sc, "level": lv,
                         "rain_total": 50.0, "rain_peak": 10.0, "p_informal": 0.9, "W": 0.0,
                         "report_depth": None})
    run = tmp_path / "replay_test"
    run.mkdir()
    pd.DataFrame(rows).to_csv(run / "scores.csv", index=False)
    (run / "map.html").write_text("<html>map</html>", encoding="utf-8")
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path)
    return "replay_test", ids


@pytest.fixture
def service(replay_run, tmp_path, monkeypatch):
    """A Service on the tiny run whose reports/photos go to tmp and whose re-score is a no-op."""
    from jolrekha import service as svc_mod

    recorded = []
    monkeypatch.setattr(svc_mod, "PHOTOS_DIR", tmp_path / "photos")
    monkeypatch.setattr(svc_mod, "add_report", lambda ward_id, depth, **kw: recorded.append(
        {"ward_id": ward_id, "depth": depth, **kw}) or recorded[-1])
    s = svc_mod.Service(replay_run[0], str(T0), rescore=lambda run: None)
    s.recorded = recorded
    return s


@pytest.fixture
def no_llm(monkeypatch):
    """Make every module see 'no Muse Spark key'."""
    from jolrekha import alerts, chatbot, vision, voice
    for mod in (alerts, chatbot, vision, voice):
        monkeypatch.setattr(mod, "get_llm", lambda: None)
    # Never reach Groq Whisper from tests, even if .env has a key
    monkeypatch.setattr(voice, "_load_dotenv", lambda: None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
