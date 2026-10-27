"""Current and next-24-hour status from the pipeline's scores.csv — the chatbot's data source."""
import pandas as pd

from . import config
from .alerts import LEVEL_ICON, LEVEL_NAMES, bn_num, localize_digits, template_alert, ward_name
from .places import find_wards

HORIZON_HOURS = 24
MAX_WARDS = 8

BN_MONTHS = ["জানুয়ারি", "ফেব্রুয়ারি", "মার্চ", "এপ্রিল", "মে", "জুন", "জুলাই",
             "আগস্ট", "সেপ্টেম্বর", "অক্টোবর", "নভেম্বর", "ডিসেম্বর"]

# Rule-based (no-LLM) chatbot phrasing
TEXT = {
    "bn": {
        "unknown": ("কোন এলাকার কথা জানতে চাইছেন বুঝতে পারিনি। এলাকার নাম বা ওয়ার্ড নম্বর লিখুন, "
                    "যেমন: মোহাম্মদপুর, যাত্রাবাড়ী, ওয়ার্ড ৪৪, সাভার।"),
        "all_clear_many": "🟢 আগামী ২৪ ঘণ্টায় এই এলাকায় পানি জমার বড় ঝুঁকি দেখা যাচ্ছে না।",
        "all_clear_one": "🟢 আগামী ২৪ ঘণ্টায় {name}-এ পানি জমার বড় ঝুঁকি দেখা যাচ্ছে না।",
        "count": "এই এলাকার {n}টা ওয়ার্ডের মধ্যে সামনের ২৪ ঘণ্টায়: {parts}।",
        "count_part": "{n}টা {level}",
        "alert_now": "এখনই সতর্কতা চলছে, ",
        "alert_from": "{time} থেকে সতর্কতা, ",
        "worst": "{icon} সবচেয়ে ঝুঁকিতে {name} — {when}সবচেয়ে খারাপ সময় {peak}।",
        "top": "সামনের ২৪ ঘণ্টায় সবচেয়ে ঝুঁকিপূর্ণ এলাকা:",
        "top_row": "{icon} {name} — সবচেয়ে খারাপ সময় {peak}",
        "top_clear": "🟢 সামনের ২৪ ঘণ্টায় কোথাও পানি জমার বড় ঝুঁকি দেখা যাচ্ছে না।",
    },
    "en": {
        "unknown": ("I couldn't tell which area you mean. Please give an area name or ward number, "
                    "e.g. Mohammadpur, Jatrabari, Ward 44, Savar."),
        "all_clear_many": "🟢 No major waterlogging risk in this area over the next 24 hours.",
        "all_clear_one": "🟢 No major waterlogging risk in {name} over the next 24 hours.",
        "count": "Of the {n} wards in this area, over the next 24 hours: {parts}.",
        "count_part": "{n} {level}",
        "alert_now": "alert in effect now, ",
        "alert_from": "alert from {time}, ",
        "worst": "{icon} Highest risk: {name} — {when}worst around {peak}.",
        "top": "Highest-risk areas over the next 24 hours:",
        "top_row": "{icon} {name} — worst around {peak}",
        "top_clear": "🟢 No major waterlogging risk anywhere over the next 24 hours.",
    },
}


def fmt_time(t: pd.Timestamp, lang: str = "bn", with_date: bool = True) -> str:
    h = t.hour
    if lang == "en":
        s = f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"
        return f"{t.day} {t.strftime('%b')}, {s}" if with_date else s
    part = ("রাত" if h < 4 else "ভোর" if h < 6 else "সকাল" if h < 12 else "দুপুর" if h < 15
            else "বিকেল" if h < 18 else "সন্ধ্যা" if h < 20 else "রাত")
    s = f"{part} {bn_num(h % 12 or 12)}টা"
    return f"{bn_num(t.day)} {BN_MONTHS[t.month - 1]} {s}" if with_date else s


class Status:
    def __init__(self, run: str = "forecast", now: str | None = None):
        path = config.OUTPUT_DIR / run / "scores.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} not found — run the pipeline first")
        self.df = pd.read_csv(path, parse_dates=["as_of"], dtype={"ward_id": str})
        times = sorted(self.df["as_of"].unique())
        self.run = run
        self.times = [pd.Timestamp(t) for t in times]
        if now:
            want = pd.Timestamp(now)
        elif run == "forecast":
            want = pd.Timestamp.now(tz=config.TIMEZONE).tz_localize(None)
        else:
            want = times[0]
        past = [t for t in times if t <= want]
        self.now = pd.Timestamp(past[-1] if past else times[0])
        self.stale = want - pd.Timestamp(times[-1]) > pd.Timedelta(hours=1)
        end = self.now + pd.Timedelta(hours=HORIZON_HOURS)
        self.window = self.df[(self.df["as_of"] >= self.now) & (self.df["as_of"] < end)]

    def _ward(self, g: pd.DataFrame) -> dict:
        g = g.sort_values("as_of")
        cur = g.iloc[0]
        peak = g.loc[g["score"].idxmax()]
        alerting = g[g["level"] != "green"]
        return {
            "ward_id": cur["ward_id"],
            "name_bn": cur["name_bn"],
            "name_en": cur["name_en"],
            "level_now": cur["level"],
            "level_peak": peak["level"],
            "peak_time": peak["as_of"],
            "alert_from": alerting["as_of"].iloc[0] if len(alerting) else None,
            "rain_mm_around_peak": round(float(peak["rain_total"])),
            "field_report": cur["report_depth"] if isinstance(cur.get("report_depth"), str) else None,
            "_peak_score": float(peak["score"]),
            "_peak_row": peak,
        }

    def for_wards(self, ids, query: str = "") -> dict:
        rows = [self._ward(g) for _, g in self.window[self.window["ward_id"].isin(list(ids))].groupby("ward_id")]
        rows.sort(key=lambda r: r["_peak_score"], reverse=True)
        return {"query": query, "now": self.now, "found": len(rows), "wards": rows}

    def place(self, query: str) -> dict:
        return self.for_wards(find_wards(query), query)

    def ward(self, ward_id: str) -> dict | None:
        rows = self.for_wards([ward_id])["wards"]
        return rows[0] if rows else None

    def top(self, n: int = 5) -> list[dict]:
        rows = [self._ward(g) for _, g in self.window.groupby("ward_id")]
        rows.sort(key=lambda r: r["_peak_score"], reverse=True)
        return rows[:n]


def public(rows: list[dict]) -> list[dict]:
    """JSON-safe view for the model: drop internal fields, ISO times, language-neutral level keys."""
    out = []
    for r in rows[:MAX_WARDS]:
        d = {k: v for k, v in r.items() if not k.startswith("_") and v is not None}
        for k in ("peak_time", "alert_from"):
            if k in d:
                d[k] = pd.Timestamp(d[k]).strftime("%Y-%m-%d %H:%M")
        out.append(d)
    return out


def summarize(result: dict, lang: str = "bn") -> str:
    """Rule-based answer without an LLM — built only from the data."""
    T = TEXT[lang]
    rows = result["wards"]
    if not rows:
        return T["unknown"]
    worst = rows[0]
    peak_row = worst["_peak_row"]
    if peak_row["level"] == "green":
        if len(rows) > 1:
            return T["all_clear_many"]
        return T["all_clear_one"].format(name=ward_name(worst, lang))

    lines = []
    if len(rows) > 1:
        counts = pd.Series([r["level_peak"] for r in rows]).value_counts()
        parts = [T["count_part"].format(n=localize_digits(str(counts[lv]), lang), level=LEVEL_NAMES[lang][lv])
                 for lv in ["red", "orange", "yellow", "green"] if lv in counts]
        lines.append(T["count"].format(n=localize_digits(str(len(rows)), lang), parts=", ".join(parts)))
    if worst["alert_from"] is None:
        when = ""
    elif worst["alert_from"] <= result["now"]:
        when = T["alert_now"]
    else:
        when = T["alert_from"].format(time=fmt_time(worst["alert_from"], lang))
    lines.append(T["worst"].format(icon=LEVEL_ICON[peak_row["level"]], name=ward_name(worst, lang),
                                   when=when, peak=fmt_time(worst["peak_time"], lang)))
    lines.append(template_alert(peak_row, lang))
    return "\n".join(lines)


def summarize_top(rows: list[dict], now, lang: str = "bn") -> str:
    """Rule-based answer for "where is it worst?" — built only from the data."""
    T = TEXT[lang]
    at_risk = [r for r in rows if r["level_peak"] != "green"]
    if not at_risk:
        return T["top_clear"]
    lines = [T["top"]] + [
        T["top_row"].format(icon=LEVEL_ICON[r["level_peak"]], name=ward_name(r, lang),
                            peak=fmt_time(r["peak_time"], lang))
        for r in at_risk
    ]
    return "\n".join(lines)
