"""Alerts, place lookup and the chatbot — without the real Muse Spark, using a fake model."""
import json

import pytest
from conftest import FakeLLM, FakeMessage, reply, tool_call

from jolrekha import alerts, chatbot, config, status
from jolrekha.places import find_wards, ward_at

pytestmark = pytest.mark.skipif(not config.WARDS_GEOJSON.exists(), reason="data/wards.geojson missing")


# ---------- place lookup ----------
@pytest.mark.parametrize("q", ["মোহাম্মদপুরে আজ পানি উঠবে?", "mohammodpur e pani uthbe?", "মোহাম্মাদপুর"])
def test_find_mohammadpur_spellings(q):
    assert len(find_wards(q)) == 6


def test_find_ward_number_and_misspelling():
    assert len(find_wards("ওয়ার্ড ৪৪")) == 1
    assert len(find_wards("যাত্রাবারি")) == len(find_wards("Jatrabari")) > 0


def test_unknown_place_finds_nothing():
    assert find_wards("আজ বৃষ্টি হবে?") == []


def test_location_to_ward():
    assert ward_at(23.758, 90.352) in find_wards("মোহাম্মদপুর")  # Beribadh side of Mohammadpur
    assert ward_at(22.0, 90.0) is None  # Bay of Bengal


# ---------- score table ----------
def test_status_picks_peak_and_alert_time(replay_run):
    run, ids = replay_run
    st = status.Status(run, "2024-05-26 18:00")
    res = st.place("মোহাম্মদপুর")
    assert res["found"] == 2
    top = res["wards"][0]
    assert top["ward_id"] == ids[0] and top["level_peak"] == "red"
    assert top["alert_from"] == res["now"]  # already yellow in the first frame
    bn = status.summarize(res, "bn")
    assert "🔴" in bn and "৯৯৯" in bn and "এখনই" in bn
    en = status.summarize(res, "en")
    assert "🔴" in en and "999" in en and "Name-" in en


# ---------- chatbot ----------
def test_chatbot_without_llm_uses_rules(replay_run, no_llm):
    st = status.Status(replay_run[0], "2024-05-26 18:00")
    assert "🔴" in chatbot.Chatbot(st).ask("মোহাম্মদপুরে পানি উঠবে?")
    assert "Highest risk" in chatbot.Chatbot(st, "en").ask("Mohammadpur")


def test_chatbot_tool_loop_answers_from_data(replay_run, monkeypatch):
    st = status.Status(replay_run[0], "2024-05-26 18:00")
    fake = FakeLLM([
        FakeMessage(content=None, tool_calls=[tool_call("get_ward_status", {"place": "মোহাম্মদপুর"})]),
        reply("মোহাম্মদপুরে লাল সতর্কতা।"),
    ])
    monkeypatch.setattr(chatbot, "get_llm", lambda: fake)
    bot = chatbot.Chatbot(st)
    assert bot.ask("মোহাম্মদপুরে পানি উঠবে?") == "মোহাম্মদপুরে লাল সতর্কতা।"
    assert "Bangla" in fake.seen[0][0]["content"]  # language rule in the system prompt
    tool_msg = fake.seen[1][-1]
    assert tool_msg["role"] == "tool"
    payload = json.loads(tool_msg["content"])
    assert payload["found"] == 2 and payload["wards"][0]["level_peak"] == "red"
    assert payload["wards"][0]["peak_time"].startswith("2024-05-26")
    assert not any(k.startswith("_") for k in payload["wards"][0])  # internal fields never reach the model


def test_chatbot_falls_back_when_llm_fails(replay_run, monkeypatch):
    st = status.Status(replay_run[0], "2024-05-26 18:00")
    monkeypatch.setattr(chatbot, "get_llm", lambda: FakeLLM([RuntimeError("network")]))
    assert "🔴" in chatbot.Chatbot(st).ask("মোহাম্মদপুর")


# ---------- alerts ----------
def _alert_rows():
    base = {"rain_total": 80.0, "rain_peak": 15.0, "p_informal": 0.9, "W": 0.0, "report_depth": None}
    return [{**base, "ward_id": "A", "name_bn": "ক", "name_en": "A", "level": "red"},
            {**base, "ward_id": "B", "name_bn": "খ", "name_en": "B", "level": "orange"}]


def test_templates_exist_for_both_languages():
    row = _alert_rows()[0]
    assert "৮০ মিমি" in alerts.template_alert(row, "bn")
    assert "80 mm" in alerts.template_alert(row, "en")


def test_alerts_use_llm_and_fill_gaps_with_template(monkeypatch):
    data = {"messages": [{"ward_id": "A", "bn": "🔴 ক: খুব ভারী বৃষ্টি, জিনিস উঁচুতে রাখুন।",
                          "en": "🔴 A: Very heavy rain, move things up high."}]}
    monkeypatch.setattr(alerts, "get_llm", lambda: FakeLLM([reply(json.dumps(data, ensure_ascii=False))]))
    msgs, source = alerts.write_alerts(_alert_rows())
    assert msgs[0]["bn"].startswith("🔴 ক:") and msgs[0]["en"].startswith("🔴 A:")
    assert msgs[1] == {lang: alerts.template_alert(_alert_rows()[1], lang) for lang in alerts.LANGS}
    assert source == "mixed"


def test_alerts_bad_json_falls_back(monkeypatch):
    monkeypatch.setattr(alerts, "get_llm", lambda: FakeLLM([reply("sorry")]))
    msgs, source = alerts.write_alerts(_alert_rows())
    assert source == "template"
    assert [m["bn"] for m in msgs] == [alerts.template_alert(r, "bn") for r in _alert_rows()]


# ---------- routed mode (small local models: model picks the tool, templates write Bangla) ----------
def test_routed_mode_recovers_garbled_place(replay_run, monkeypatch):
    st = status.Status(replay_run[0], "2024-05-26 18:00")
    monkeypatch.setenv("JOLREKHA_LLM_REPLY_LANGS", "en")
    fake = FakeLLM([FakeMessage(content=None, tool_calls=[tool_call("get_ward_status", {"place": "জসাারা সিপিশ"})])])
    monkeypatch.setattr(chatbot, "get_llm", lambda: fake)
    answer = chatbot.Chatbot(st, "bn").ask("মোহাম্মদপুরে পানি উঠবে?")
    assert "🔴" in answer and "৯৯৯" in answer  # template Bangla from the user's own words
    assert len(fake.seen) == 1  # one routing call, no free-form Bangla from the model


def test_routed_mode_top_risk(replay_run, monkeypatch):
    st = status.Status(replay_run[0], "2024-05-26 18:00")
    monkeypatch.setenv("JOLREKHA_LLM_REPLY_LANGS", "en")
    monkeypatch.setattr(chatbot, "get_llm", lambda: FakeLLM([FakeMessage(
        content=None, tool_calls=[tool_call("get_top_risk_wards", {"limit": "10"})])]))
    answer = chatbot.Chatbot(st, "bn").ask("সবচেয়ে বেশি ঝুঁকি কোথায়?")
    assert answer.startswith("সামনের ২৪ ঘণ্টায় সবচেয়ে ঝুঁকিপূর্ণ") and "🔴" in answer


def test_alerts_stay_on_templates_when_model_not_trusted_with_bangla(monkeypatch):
    monkeypatch.setenv("JOLREKHA_LLM_REPLY_LANGS", "en")
    fake = FakeLLM([])
    monkeypatch.setattr(alerts, "get_llm", lambda: fake)
    msgs, source = alerts.write_alerts(_alert_rows())
    assert source == "template" and not fake.seen
