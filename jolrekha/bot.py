"""Jolrekha Telegram bot — where residents subscribe, get alerts, ask, and report water.

    python -m jolrekha.bot                                     # live forecast, refreshed hourly
    python -m jolrekha.bot --demo replay_2024-05-27 --start "2024-05-26 12:00" --speed 20
                                                               # replay: 1 simulated hour every 20 s

Needs TELEGRAM_BOT_TOKEN in .env (from @BotFather). Uses the plain Bot API over
HTTPS long polling — no extra dependencies.

What people can do:
  share location / "/subscribe মোহাম্মদপুর"  → follow their ward, get pushed alerts
  type or send a voice note                  → chatbot answer (Muse Spark, rules without a key)
  send a photo of the street                  → Muse Spark judges the depth, or they tap a button
"""
import argparse
import os
import secrets
import sys
import time

import requests

from .chatbot import Chatbot
from .llm import _load_dotenv
from .notify import Subscribers, due_alerts
from .places import find_wards, ward_at, ward_names
from .service import Service
from .status import summarize
from .voice import transcribe

DEPTHS = ["ankle", "knee", "waist", "none"]

TEXT = {
    "bn": {
        "welcome": ("জলরেখায় স্বাগতম! 🌧️\nআপনার এলাকায় পানি ওঠার আগে আমরা সতর্ক করব।\n\n"
                    "১. নিচের বোতাম চেপে লোকেশন পাঠান, অথবা লিখুন: /subscribe মোহাম্মদপুর\n"
                    "২. প্রশ্ন করুন, লিখে বা ভয়েসে: \"আজ পানি উঠবে?\"\n"
                    "৩. রাস্তায় পানি দেখলে ছবি পাঠান — অন্যদের সতর্ক করতে সাহায্য হবে।"),
        "location_button": "📍 আমার এলাকা পাঠান",
        "subscribed": "✅ এখন থেকে এই এলাকার সতর্কতা পাবেন:\n{names}",
        "already": "আপনি আগেই এই এলাকার সতর্কতা পাচ্ছেন।",
        "not_found": "এলাকাটা চিনতে পারিনি। লোকেশন পাঠান, অথবা থানা/ওয়ার্ডের নাম লিখুন, যেমন: /subscribe যাত্রাবাড়ী",
        "outside": "এই লোকেশন ঢাকা জেলার বাইরে। জলরেখা এখন শুধু ঢাকা জেলার জন্য।",
        "stopped": "সতর্কতা বন্ধ করা হলো। আবার চালু করতে /start লিখুন।",
        "no_sub": "আপনি এখনো কোনো এলাকা বেছে নেননি। লোকেশন পাঠান বা /subscribe <এলাকা> লিখুন।",
        "lang": "ভাষা: বাংলা",
        "photo_where": "ধন্যবাদ! ছবিটা কোন এলাকার? লোকেশন পাঠান 📍",
        "photo_ok": "🙏 ধন্যবাদ! ছবিতে {depth} পানি দেখা যাচ্ছে। রিপোর্ট যোগ হয়েছে — {name}-এর ঝুঁকি হালনাগাদ হলো।",
        "photo_dry": "ধন্যবাদ! ছবিতে জমা পানি দেখা যাচ্ছে না। পানি দেখলে আবার ছবি পাঠাবেন।",
        "photo_ask": "ধন্যবাদ! পানি কতটা? নিচে বেছে নিন:",
        "depth_saved": "🙏 ধন্যবাদ! {name}: {depth} পানির রিপোর্ট যোগ হয়েছে।",
        "depth_none_saved": "ধন্যবাদ! পানি নেই — জেনে রাখলাম।",
        "voice_fail": "দুঃখিত, ভয়েসটা বুঝতে পারিনি। একটু লিখে পাঠাবেন?",
        "voice_heard": "🎤 শুনলাম: \"{text}\"",
        "expired": "এই রিপোর্টের সময় পেরিয়ে গেছে, ছবিটা আবার পাঠান।",
        "depth": {"ankle": "গোড়ালি", "knee": "হাঁটু", "waist": "কোমর", "none": "পানি নেই"},
    },
    "en": {
        "welcome": ("Welcome to Jolrekha! 🌧️\nWe warn you before water rises in your area.\n\n"
                    "1. Tap the button below to share your location, or type: /subscribe Mohammadpur\n"
                    "2. Ask by text or voice: \"Will water rise today?\"\n"
                    "3. See water on the street? Send a photo — it helps warn others."),
        "location_button": "📍 Send my area",
        "subscribed": "✅ You'll now get alerts for:\n{names}",
        "already": "You're already getting alerts for this area.",
        "not_found": "I couldn't find that area. Share your location, or give a thana/ward name, e.g. /subscribe Jatrabari",
        "outside": "That location is outside Dhaka district. Jolrekha currently covers Dhaka district only.",
        "stopped": "Alerts stopped. Type /start to turn them back on.",
        "no_sub": "You haven't picked an area yet. Share your location or type /subscribe <area>.",
        "lang": "Language: English",
        "photo_where": "Thanks! Which area is this photo from? Please share your location 📍",
        "photo_ok": "🙏 Thanks! The photo shows {depth}-deep water. Report added — {name}'s risk is updated.",
        "photo_dry": "Thanks! No standing water is visible. Send another photo if you see water.",
        "photo_ask": "Thanks! How deep is the water? Pick one:",
        "depth_saved": "🙏 Thanks! {name}: {depth}-deep water report added.",
        "depth_none_saved": "Thanks! No water — noted.",
        "voice_fail": "Sorry, I couldn't understand the voice note. Could you type it?",
        "voice_heard": "🎤 I heard: \"{text}\"",
        "expired": "This report has expired, please send the photo again.",
        "depth": {"ankle": "ankle", "knee": "knee", "waist": "waist", "none": "no water"},
    },
}


class TelegramAPI:
    def __init__(self, token: str, session: requests.Session | None = None):
        self.base = f"https://api.telegram.org/bot{token}/"
        self.file_base = f"https://api.telegram.org/file/bot{token}/"
        self.session = session or requests.Session()

    def call(self, method: str, **params):
        r = self.session.post(self.base + method, json=params, timeout=70)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"{method}: {data.get('description')}")
        return data["result"]

    def download(self, file_id: str) -> bytes:
        path = self.call("getFile", file_id=file_id)["file_path"]
        r = self.session.get(self.file_base + path, timeout=60)
        r.raise_for_status()
        return r.content


class JolrekhaBot:
    def __init__(self, api, service: Service, subs: Subscribers | None = None):
        self.api = api
        self.svc = service
        self.subs = subs or Subscribers()
        self.chats: dict[str, Chatbot] = {}
        self.pending: dict[str, dict] = {}  # report key → {"chat", "ward", "image"?}

    # ---------- helpers ----------
    def lang(self, chat_id) -> str:
        return self.subs.get(chat_id)["lang"]

    def t(self, chat_id, key, **kw):
        s = TEXT[self.lang(chat_id)][key]
        return s.format(**kw) if kw else s

    def send(self, chat_id, text, **kw):
        return self.api.call("sendMessage", chat_id=chat_id, text=text, **kw)

    def chatbot(self, chat_id) -> Chatbot:
        key = str(chat_id)
        bot = self.chats.get(key)
        if bot is None or bot.lang != self.lang(chat_id) or bot.status is not self.svc.status:
            bot = self.chats[key] = Chatbot(self.svc.status, self.lang(chat_id))
        return bot

    def _names(self, chat_id, ward_ids) -> str:
        lang = self.lang(chat_id)
        names = [ward_names(w)[lang] for w in ward_ids]
        more = len(names) - 6
        return "\n".join(f"• {n}" for n in names[:6]) + (f"\n… +{more}" if more > 0 else "")

    # ---------- dispatch ----------
    def handle(self, update: dict):
        if "callback_query" in update:
            return self.on_callback(update["callback_query"])
        msg = update.get("message")
        if not msg:
            return
        chat_id = msg["chat"]["id"]
        if "location" in msg:
            return self.on_location(chat_id, msg["location"])
        if "photo" in msg:
            return self.on_photo(chat_id, msg["photo"][-1]["file_id"], msg.get("caption", ""))
        if "voice" in msg:
            return self.on_voice(chat_id, msg["voice"]["file_id"])
        text = (msg.get("text") or "").strip()
        if not text:
            return
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd == "/start":
            return self.on_start(chat_id)
        if cmd == "/subscribe":
            return self.on_subscribe(chat_id, arg)
        if cmd == "/stop":
            self.subs.unsubscribe(chat_id)
            return self.send(chat_id, TEXT["bn"]["stopped"] + "\n" + TEXT["en"]["stopped"])
        if cmd == "/status":
            return self.on_status(chat_id)
        if cmd == "/lang":
            self.subs.set_lang(chat_id, "en" if self.lang(chat_id) == "bn" else "bn")
            return self.send(chat_id, self.t(chat_id, "lang"))
        return self.send(chat_id, self.chatbot(chat_id).ask(text))

    # ---------- handlers ----------
    def on_start(self, chat_id):
        self.subs.get(chat_id)
        self.subs.save()
        kb = {"keyboard": [[{"text": self.t(chat_id, "location_button"), "request_location": True}]],
              "resize_keyboard": True}
        return self.send(chat_id, self.t(chat_id, "welcome"), reply_markup=kb)

    def on_subscribe(self, chat_id, place: str):
        ids = find_wards(place) if place else []
        if not ids:
            return self.send(chat_id, self.t(chat_id, "not_found"))
        return self._subscribe(chat_id, ids)

    def _subscribe(self, chat_id, ids):
        added = self.subs.subscribe(chat_id, ids)
        if not added:
            return self.send(chat_id, self.t(chat_id, "already"))
        self.send(chat_id, self.t(chat_id, "subscribed", names=self._names(chat_id, added)))
        return self.send(chat_id, summarize(self.svc.status.for_wards(added), self.lang(chat_id)))

    def on_status(self, chat_id):
        wards = self.subs.get(chat_id)["wards"]
        if not wards:
            return self.send(chat_id, self.t(chat_id, "no_sub"))
        return self.send(chat_id, summarize(self.svc.status.for_wards(wards), self.lang(chat_id)))

    def on_location(self, chat_id, loc):
        ward = ward_at(loc["latitude"], loc["longitude"])
        if ward is None:
            return self.send(chat_id, self.t(chat_id, "outside"))
        waiting = [k for k, p in self.pending.items() if p["chat"] == str(chat_id) and p.get("ward") is None]
        if waiting:  # a photo was waiting for its location
            p = self.pending.pop(waiting[-1])
            return self._process_photo(chat_id, p["image"], ward)
        return self._subscribe(chat_id, [ward])

    def on_photo(self, chat_id, file_id, caption: str):
        image = self.api.download(file_id)
        ids = find_wards(caption) if caption else []
        if len(ids) != 1:
            own = self.subs.get(chat_id)["wards"]
            ids = own if len(own) == 1 else []
        if not ids:  # don't guess the ward — ask for a location
            self.pending[secrets.token_hex(4)] = {"chat": str(chat_id), "ward": None, "image": image}
            return self.send(chat_id, self.t(chat_id, "photo_where"))
        return self._process_photo(chat_id, image, ids[0])

    def _process_photo(self, chat_id, image: bytes, ward: str):
        name = ward_names(ward)[self.lang(chat_id)]
        res = self.svc.photo_report(image, ward, source="telegram")
        if res["status"] == "recorded":
            depth = TEXT[self.lang(chat_id)]["depth"][res["depth"]]
            return self.send(chat_id, self.t(chat_id, "photo_ok", depth=depth, name=name))
        if res["status"] == "no_water":
            return self.send(chat_id, self.t(chat_id, "photo_dry"))
        key = secrets.token_hex(4)
        self.pending[key] = {"chat": str(chat_id), "ward": ward}
        labels = TEXT[self.lang(chat_id)]["depth"]
        kb = {"inline_keyboard": [[{"text": labels[d], "callback_data": f"d|{key}|{d}"} for d in DEPTHS]]}
        return self.send(chat_id, self.t(chat_id, "photo_ask"), reply_markup=kb)

    def on_callback(self, cq: dict):
        self.api.call("answerCallbackQuery", callback_query_id=cq["id"])
        chat_id = cq["message"]["chat"]["id"]
        try:
            _, key, depth = cq.get("data", "").split("|")
        except ValueError:
            return
        p = self.pending.pop(key, None)
        if p is None or p["ward"] is None or depth not in DEPTHS:
            return self.send(chat_id, self.t(chat_id, "expired"))
        if depth == "none":
            return self.send(chat_id, self.t(chat_id, "depth_none_saved"))
        # The user's own judgement, not model-checked → counts at half weight
        self.svc.record(p["ward"], depth, verified=False, source="telegram")
        name = ward_names(p["ward"])[self.lang(chat_id)]
        depth_label = TEXT[self.lang(chat_id)]["depth"][depth]
        return self.send(chat_id, self.t(chat_id, "depth_saved", name=name, depth=depth_label))

    def on_voice(self, chat_id, file_id):
        text = transcribe(self.api.download(file_id), "ogg")
        if not text:
            return self.send(chat_id, self.t(chat_id, "voice_fail"))
        answer = self.chatbot(chat_id).ask(text)
        return self.send(chat_id, f"{self.t(chat_id, 'voice_heard', text=text)}\n\n{answer}")

    # ---------- alerts ----------
    def push_alerts(self) -> int:
        sent = 0
        for chat_id, text in due_alerts(self.svc.status, self.subs):
            try:
                self.send(chat_id, text)
                sent += 1
            except Exception as e:  # blocked bot, deleted chat … keep going
                print(f"⚠ could not alert {chat_id}: {e}", file=sys.stderr)
        self.subs.save()
        return sent


def run_polling(bot: JolrekhaBot, tick_seconds: float, tick):
    """Long-poll Telegram; call tick() every tick_seconds (refresh/advance + push alerts)."""
    offset, next_tick = None, 0.0
    while True:
        if time.monotonic() >= next_tick:
            try:
                tick()
            except Exception as e:
                print(f"⚠ tick failed: {e}", file=sys.stderr)
            next_tick = time.monotonic() + tick_seconds
        try:
            updates = bot.api.call("getUpdates", timeout=min(30, max(1, int(tick_seconds))), offset=offset)
        except Exception as e:
            print(f"⚠ getUpdates failed: {e}", file=sys.stderr)
            time.sleep(5)
            continue
        for u in updates:
            offset = u["update_id"] + 1
            try:
                bot.handle(u)
            except Exception as e:  # one bad update must not stop the bot
                print(f"⚠ update {u.get('update_id')} failed: {e}", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description="Jolrekha Telegram bot")
    ap.add_argument("--demo", help="replay run to play back, e.g. replay_2024-05-27")
    ap.add_argument("--start", help="replay start time, e.g. '2024-05-26 12:00'")
    ap.add_argument("--speed", type=float, default=20, help="seconds per simulated hour in demo mode")
    ap.add_argument("--refresh-min", type=float, default=60, help="live mode: minutes between forecast refreshes")
    args = ap.parse_args()

    _load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN is missing — get one from @BotFather and put it in .env")

    if args.demo:
        svc = Service(args.demo, args.start)
        bot = JolrekhaBot(TelegramAPI(token), svc)
        for s in bot.subs.data.values():  # each demo run starts from a clean slate
            s["last_level"] = {}
        first = [True]

        def tick():
            if not first[0] and not svc.advance(1):
                return
            first[0] = False
            print(f"⏱ demo clock {svc.status.now} · alerts sent: {bot.push_alerts()}")
        print(f"Jolrekha bot · demo {args.demo} from {svc.status.now} · {args.speed}s per hour")
        run_polling(bot, args.speed, tick)
    else:
        svc = Service("forecast")
        bot = JolrekhaBot(TelegramAPI(token), svc)

        def tick():
            svc.refresh_live()
            print(f"⏱ forecast refreshed {svc.status.now} · alerts sent: {bot.push_alerts()}")
        print("Jolrekha bot · live forecast")
        run_polling(bot, args.refresh_min * 60, tick)


if __name__ == "__main__":
    main()
