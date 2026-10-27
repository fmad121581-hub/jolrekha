"""Subscribers and alert push — who gets told what, and when.

A subscriber is a chat (Telegram today) following one or more wards. On every
refresh we look at each followed ward's worst level over the next 24 hours and
send a message only when it *rises* to orange/red, or falls back to green after
an alert — never the same level twice, so people don't learn to ignore it.
"""
import json
import threading

from . import config
from .alerts import LEVEL_ICON, template_alert, write_alerts
from .status import Status, fmt_time

SUBSCRIBERS_JSON = config.DATA_DIR / "subscribers.json"
NOTIFY_LEVELS = {"orange", "red"}
LEVEL_RANK = {"green": 0, "yellow": 1, "orange": 2, "red": 3}

ALL_CLEAR = {
    "bn": "🟢 {name}: বিপদ কেটে গেছে, সামনের ২৪ ঘণ্টায় পানি জমার বড় ঝুঁকি নেই।",
    "en": "🟢 {name}: The danger has passed — no major waterlogging risk in the next 24 hours.",
}
WHEN = {"bn": "সবচেয়ে খারাপ সময়: {time}", "en": "Worst around: {time}"}


class Subscribers:
    """chat_id → {"wards": [...], "lang": "bn", "last_level": {ward_id: level}}, persisted as JSON."""

    def __init__(self, path=SUBSCRIBERS_JSON):
        self.path = path
        self._lock = threading.Lock()
        self.data: dict[str, dict] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def save(self):
        with self._lock:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get(self, chat_id) -> dict:
        return self.data.setdefault(str(chat_id), {"wards": [], "lang": "bn", "last_level": {}})

    def subscribe(self, chat_id, ward_ids: list[str]) -> list[str]:
        s = self.get(chat_id)
        added = [w for w in ward_ids if w not in s["wards"]]
        s["wards"].extend(added)
        self.save()
        return added

    def unsubscribe(self, chat_id):
        self.data.pop(str(chat_id), None)
        self.save()

    def set_lang(self, chat_id, lang: str):
        self.get(chat_id)["lang"] = lang
        self.save()


def _rank(level: str | None) -> int:
    return LEVEL_RANK.get(level or "green", 0)


def due_alerts(status: Status, subs: Subscribers, use_llm: bool = True) -> list[tuple[str, str]]:
    """[(chat_id, text)] to send now. Updates each subscriber's last_level (caller saves)."""
    pending = []  # (chat_id, lang, ward status, kind)
    for chat_id, s in subs.data.items():
        for wid in s["wards"]:
            w = status.ward(wid)
            if w is None:
                continue
            new, old = w["level_peak"], s["last_level"].get(wid, "green")
            if new in NOTIFY_LEVELS and _rank(new) > _rank(old):
                pending.append((chat_id, s["lang"], w, "alert"))
            elif new == "green" and old in NOTIFY_LEVELS:
                pending.append((chat_id, s["lang"], w, "clear"))
            # Track downgrades silently too, so a later re-escalation alerts again
            s["last_level"][wid] = new

    # One model call for all wards that need an alert (falls back to templates per ward)
    alert_rows = [p[2]["_peak_row"].to_dict() for p in pending if p[3] == "alert"]
    written = write_alerts(alert_rows)[0] if (use_llm and alert_rows) else \
        [{lang: template_alert(r, lang) for lang in ("bn", "en")} for r in alert_rows]
    by_ward = {r["ward_id"]: m for r, m in zip(alert_rows, written)}

    out = []
    for chat_id, lang, w, kind in pending:
        name = w["name_bn"] if lang == "bn" else w["name_en"]
        if kind == "clear":
            out.append((chat_id, ALL_CLEAR[lang].format(name=name)))
        else:
            when = WHEN[lang].format(time=fmt_time(w["peak_time"], lang))
            out.append((chat_id, f"{by_ward[w['ward_id']][lang]}\n{LEVEL_ICON[w['level_peak']]} {when}"))
    return out
