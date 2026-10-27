"""Telegram bot, alert push, photo/voice analysis and the web demo — with fakes, no network."""
import base64
import json

import pytest
from conftest import FakeLLM, reply

from jolrekha import bot as bot_mod
from jolrekha import config, notify, vision, voice
from jolrekha.server import DemoApp

pytestmark = pytest.mark.skipif(not config.WARDS_GEOJSON.exists(), reason="data/wards.geojson missing")

JPEG = b"\xff\xd8\xff\xe0fake-jpeg"


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def call(self, method, **params):
        self.sent.append((method, params))
        return {"ok": True}

    def download(self, file_id):
        return JPEG if file_id.startswith("photo") else b"OggS-voice"

    def texts(self):
        return [p["text"] for m, p in self.sent if m == "sendMessage"]


@pytest.fixture
def tg(service, tmp_path, no_llm):
    api = FakeTelegram()
    b = bot_mod.JolrekhaBot(api, service, notify.Subscribers(tmp_path / "subs.json"))
    return api, b


def msg(chat=1, **kw):
    return {"message": {"chat": {"id": chat}, **kw}}


# ---------- bot ----------
def test_start_offers_location_button(tg):
    api, b = tg
    b.handle(msg(text="/start"))
    method, p = api.sent[-1]
    assert "জলরেখায় স্বাগতম" in p["text"]
    assert p["reply_markup"]["keyboard"][0][0]["request_location"] is True


def test_subscribe_by_name_and_status(tg, replay_run):
    api, b = tg
    b.handle(msg(text="/subscribe মোহাম্মদপুর"))
    assert set(b.subs.get(1)["wards"]) >= set(replay_run[1])
    assert "✅" in api.texts()[-2] and "🔴" in api.texts()[-1]
    b.handle(msg(text="/subscribe মোহাম্মদপুর"))
    assert "আগেই" in api.texts()[-1]


def test_location_subscribes_to_containing_ward(tg):
    api, b = tg
    b.handle(msg(location={"latitude": 23.758, "longitude": 90.352}))
    assert len(b.subs.get(1)["wards"]) == 1
    b.handle(msg(chat=2, location={"latitude": 22.0, "longitude": 90.0}))
    assert "বাইরে" in api.texts()[-1]


def test_free_text_goes_to_chatbot(tg):
    api, b = tg
    b.handle(msg(text="যাত্রাবাড়ীতে পানি উঠবে?"))
    assert api.texts()[-1]  # rule-based answer, no crash


def test_lang_toggle(tg):
    api, b = tg
    b.handle(msg(text="/lang"))
    assert b.lang(1) == "en"
    b.handle(msg(text="/start"))
    assert "Welcome to Jolrekha" in api.texts()[-1]


def test_photo_without_area_asks_for_location_then_depth(tg, service, replay_run):
    api, b = tg
    b.handle(msg(photo=[{"file_id": "photo-small"}, {"file_id": "photo-big"}]))
    assert "লোকেশন" in api.texts()[-1]
    b.handle(msg(location={"latitude": 23.758, "longitude": 90.352}))
    method, p = api.sent[-1]
    buttons = p["reply_markup"]["inline_keyboard"][0]
    knee = next(x for x in buttons if x["callback_data"].endswith("|knee"))
    b.handle({"callback_query": {"id": "q1", "data": knee["callback_data"], "message": {"chat": {"id": 1}}}})
    assert service.recorded[-1]["depth"] == "knee" and service.recorded[-1]["verified"] is False
    assert "হাঁটু" in api.texts()[-1]


def test_photo_with_caption_and_confident_model_is_recorded(tg, service, monkeypatch):
    api, b = tg
    monkeypatch.setattr(vision, "get_llm", lambda: FakeLLM([reply(json.dumps(
        {"water_visible": True, "depth": "waist", "confidence": 0.9, "evidence": "water at rickshaw seat"}))]))
    b.handle(msg(photo=[{"file_id": "photo-1"}], caption="ওয়ার্ড ৪৪"))
    assert service.recorded[-1]["depth"] == "waist" and service.recorded[-1]["verified"] is True
    assert "কোমর" in api.texts()[-1]


def test_stale_depth_button_is_rejected(tg, service):
    api, b = tg
    b.handle({"callback_query": {"id": "q", "data": "d|nope|knee", "message": {"chat": {"id": 1}}}})
    assert not service.recorded and "আবার" in api.texts()[-1]


def test_voice_without_model_asks_to_type(tg):
    api, b = tg
    b.handle(msg(voice={"file_id": "voice-1"}))
    assert "লিখে" in api.texts()[-1]


def test_voice_with_model_answers_transcript(tg, monkeypatch):
    api, b = tg
    monkeypatch.setattr(voice, "get_llm", lambda: FakeLLM([reply("মোহাম্মদপুরে পানি উঠবে?")]))
    b.handle(msg(voice={"file_id": "voice-1"}))
    assert "🎤" in api.texts()[-1] and "মোহাম্মদপুরে" in api.texts()[-1]


# ---------- alert push ----------
def test_push_only_on_rising_level(tg, service, replay_run):
    api, b = tg
    a, green_ward = replay_run[1]
    b.subs.subscribe(1, [a, green_ward])
    assert b.push_alerts() == 1  # ward A peaks red within 24 h; ward B stays green
    assert "🔴" in api.texts()[-1]
    assert b.push_alerts() == 0  # same level again → silent


def test_all_clear_after_alert(service, tmp_path, replay_run):
    subs = notify.Subscribers(tmp_path / "s.json")
    subs.subscribe(7, [replay_run[1][1]])
    subs.get(7)["last_level"][replay_run[1][1]] = "red"
    out = notify.due_alerts(service.status, subs, use_llm=False)
    assert out and out[0][1].startswith("🟢")


# ---------- vision / voice parsing ----------
def test_vision_rejects_unknown_depth(monkeypatch):
    monkeypatch.setattr(vision, "get_llm", lambda: FakeLLM([reply('{"water_visible": true, "depth": "chest"}')]))
    assert vision.analyze_photo(JPEG) is None


def test_vision_no_water_overrides_depth(monkeypatch):
    monkeypatch.setattr(vision, "get_llm", lambda: FakeLLM([reply(
        '{"water_visible": false, "depth": "knee", "confidence": 0.8}')]))
    assert vision.analyze_photo(JPEG)["depth"] == "none"


def test_vision_sends_image_as_data_url(monkeypatch):
    fake = FakeLLM([reply('{"water_visible": true, "depth": "ankle", "confidence": 0.7}')])
    monkeypatch.setattr(vision, "get_llm", lambda: fake)
    vision.analyze_photo(b"\x89PNG....")
    part = fake.seen[0][0]["content"][1]
    assert part["type"] == "image_url" and part["image_url"]["url"].startswith("data:image/png;base64,")


# ---------- web demo ----------
def test_web_ask_and_time(service, no_llm):
    app = DemoApp(service)
    st = app.state()
    assert st["now"] == "2024-05-26 18:00" and len(st["frames"]) == 4 and st["llm"] is False
    assert "🔴" in app.ask({"q": "মোহাম্মদপুর", "lang": "bn", "session": "x"})["answer"]
    assert app.set_time({"now": "2024-05-26 20:00"})["now"] == "2024-05-26 20:00"


def test_web_report_depth_and_photo(service, replay_run, no_llm):
    app = DemoApp(service)
    ward = replay_run[1][0]
    r = app.report({"ward_id": ward, "depth": "knee", "lang": "en"})
    assert r["ok"] and r["status"] == "recorded" and service.recorded[-1]["source"] == "web"
    img = "data:image/jpeg;base64," + base64.b64encode(JPEG).decode()
    r = app.report({"ward_id": ward, "image_b64": img})
    assert r["ok"] and r["status"] == "needs_depth"  # no model → ask the reporter
    assert app.report({"place": "আজ বৃষ্টি", "depth": "knee"})["error"] == "ward_unknown"
    assert app.report({"ward_id": ward, "depth": "chest"})["error"] == "bad_depth"


# ---------- real HTTP against a local fake Telegram server ----------
def test_telegram_api_over_http():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    seen = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _reply(self, body: bytes, ctype="application/json"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen.append((self.path, body))
            if self.path.endswith("/getFile"):
                return self._reply(json.dumps({"ok": True, "result": {"file_path": "photos/a.jpg"}}).encode())
            if self.path.endswith("/badMethod"):
                return self._reply(b'{"ok": false, "description": "Not Found"}')
            self._reply(json.dumps({"ok": True, "result": {"message_id": 1}}).encode())

        def do_GET(self):
            seen.append((self.path, None))
            self._reply(JPEG, "image/jpeg")

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    api = bot_mod.TelegramAPI("TEST:TOKEN")
    api.base = f"http://127.0.0.1:{srv.server_port}/botTEST:TOKEN/"
    api.file_base = f"http://127.0.0.1:{srv.server_port}/file/botTEST:TOKEN/"
    try:
        assert api.call("sendMessage", chat_id=1, text="হ্যালো") == {"message_id": 1}
        assert seen[-1][1]["text"] == "হ্যালো"
        assert api.download("abc") == JPEG
        assert seen[-1][0] == "/file/botTEST:TOKEN/photos/a.jpg"
        with pytest.raises(RuntimeError, match="Not Found"):
            api.call("badMethod")
    finally:
        srv.shutdown()
