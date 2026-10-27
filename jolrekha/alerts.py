"""Alert messages — Bangla for residents, English for judges/demo.

With Muse Spark the model writes a separate message per ward (several wards per
request, both languages at once). Without a key, or if the model fails, the
templates below are used. Every user-facing string has a "bn" and an "en" version.
"""
import json
import os

from .llm import get_llm, reply_langs

LANGS = ("bn", "en")
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

LEVEL_NAMES = {
    "bn": {"red": "লাল", "orange": "কমলা", "yellow": "হলুদ", "green": "সবুজ"},
    "en": {"red": "Red", "orange": "Orange", "yellow": "Yellow", "green": "Green"},
}
LEVEL_ICON = {"red": "🔴", "orange": "🟠", "yellow": "🟡", "green": "🟢"}

TEMPLATES = {
    "bn": {
        "red": (
            "🔴 {name}: সতর্ক থাকুন! সামনের কয়েক ঘণ্টায় খুব ভারী বৃষ্টিতে রাস্তা ও ঘরে পানি ঢোকার "
            "ঝুঁকি বেশি।{rain} ওষুধ, কাগজপত্র আর দরকারি জিনিস উঁচু জায়গায় রাখুন। বিদ্যুতের তার "
            "ও খোলা ড্রেন থেকে দূরে থাকুন। জরুরি প্রয়োজনে ৯৯৯-এ ফোন করুন।"
        ),
        "orange": (
            "🟠 {name}: আজ ভারী বৃষ্টির সম্ভাবনা, নিচু রাস্তায় পানি জমতে পারে।{rain} বের হওয়ার আগে "
            "পথ দেখে নিন, শিশুদের ড্রেনের কাছে যেতে দেবেন না।"
        ),
        "yellow": "🟡 {name}: বৃষ্টি হতে পারে, কিছু রাস্তায় অল্প পানি জমতে পারে।{rain} খবর রাখুন।",
        "green": "🟢 {name}: এই মুহূর্তে পানি জমার বড় ঝুঁকি দেখা যাচ্ছে না।",
    },
    "en": {
        "red": (
            "🔴 {name}: Take care! Very heavy rain in the next few hours could flood roads and homes."
            "{rain} Move medicine, documents and valuables up high. Stay away from power lines and "
            "open drains. In an emergency, call 999."
        ),
        "orange": (
            "🟠 {name}: Heavy rain likely today; low-lying roads may flood.{rain} Check your route "
            "before going out and keep children away from drains."
        ),
        "yellow": "🟡 {name}: Rain possible; some roads may get a little water.{rain} Stay updated.",
        "green": "🟢 {name}: No major waterlogging risk right now.",
    },
}
RAIN_NOTE = {"bn": " (আনুমানিক {mm} মিমি বৃষ্টি)", "en": " (about {mm} mm of rain)"}

ALERT_SYSTEM = """You write SMS-style flood/waterlogging alerts for "Jolrekha" (জলরেখা), a warning
system for Dhaka. Readers include rickshaw pullers and domestic workers in informal settlements,
many of whom cannot read English, so the Bangla message is the one that matters.

For each area, write:
- "bn": simple spoken Bangla, no English words, understandable in one read.
- "en": a faithful English rendering of the same message (for judges and partners).

Rules (both languages):
- At most 3 sentences, under 250 characters. Start with the level icon (🔴/🟠/🟡) and the area name.
- Use only the facts given. Never invent numbers, street names or events.
- Give one practical action that fits the level (red: move belongings up, keep away from
  electricity and drains, call 999 in an emergency; orange: check the route before going out;
  yellow: stay updated).
- If a field report exists, mention it (e.g. "knee-deep water reported in the area").
- Do not cause panic, and do not play down the risk.

Reply with JSON only: {"messages": [{"ward_id": "...", "bn": "...", "en": "..."}]}"""

DEPTH_EN = {"ankle": "ankle-deep", "knee": "knee-deep", "waist": "waist-deep"}
BATCH = int(os.environ.get("JOLREKHA_ALERT_BATCH", 20))  # smaller for slow local models


def localize_digits(s: str, lang: str) -> str:
    return s.translate(BN_DIGITS) if lang == "bn" else s


def bn_num(x) -> str:
    return str(x).translate(BN_DIGITS)


def ward_name(row, lang: str) -> str:
    return row["name_bn"] if lang == "bn" else row["name_en"]


def template_alert(row, lang: str = "bn") -> str:
    rain = ""
    if row["rain_total"] >= 1:
        rain = localize_digits(RAIN_NOTE[lang].format(mm=round(row["rain_total"])), lang)
    return TEMPLATES[lang][row["level"]].format(name=ward_name(row, lang), rain=rain)


def _facts(row) -> dict:
    f = {
        "ward_id": row["ward_id"],
        "name_bn": row["name_bn"],
        "name_en": row["name_en"],
        "level": row["level"],
        "rain_next_hours_mm": round(float(row["rain_total"])),
        "heaviest_hour_mm": round(float(row["rain_peak"])),
        "dense_informal_settlement": bool(row["p_informal"] >= 0.6),
    }
    if row.get("W", 0) > 0 and isinstance(row.get("report_depth"), str):
        f["field_report"] = DEPTH_EN.get(row["report_depth"], row["report_depth"]) + " water reported"
    return f


def _valid(msg) -> bool:
    return isinstance(msg, str) and 10 < len(msg) <= 400


def write_alerts(rows: list[dict]) -> tuple[list[dict], str]:
    """Messages for many wards at once.

    Returns ([{"bn": ..., "en": ...}, ...], source) with source = the model name | "template" | "mixed".
    """
    out = [{lang: template_alert(r, lang) for lang in LANGS} for r in rows]
    llm = get_llm()
    # Residents read the Bangla: if the model isn't trusted to write Bangla, keep both
    # languages on templates so the বাংলা/English switch always shows the same message.
    if llm is None or not rows or "bn" not in reply_langs():
        return out, "template"

    used_llm = 0
    for i in range(0, len(rows), BATCH):
        chunk = rows[i:i + BATCH]
        try:
            data = llm.json([
                {"role": "system", "content": ALERT_SYSTEM},
                {"role": "user", "content": json.dumps([_facts(r) for r in chunk], ensure_ascii=False)},
            ])
            by_id = {m["ward_id"]: m for m in data.get("messages", [])}
        except Exception as e:  # network/JSON — this batch stays on templates
            print(f"⚠ model failed (batch {i // BATCH + 1}): {e}")
            continue
        for j, r in enumerate(chunk):
            m = by_id.get(r["ward_id"], {})
            # Bangla is what residents read: only count the ward as model-written if bn is valid
            if _valid(m.get("bn")):
                out[i + j]["bn"] = m["bn"].strip()
                used_llm += 1
                if _valid(m.get("en")):
                    out[i + j]["en"] = m["en"].strip()
    model = getattr(llm, "model", "llm")
    source = model if used_llm == len(rows) else ("template" if used_llm == 0 else "mixed")
    return out, source
