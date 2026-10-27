"""The whole pipeline in one command.

    python -m jolrekha.pipeline --mode replay            # Cyclone Remal, 27 May 2024
    python -m jolrekha.pipeline --mode replay --date 2022-10-24
    python -m jolrekha.pipeline --mode forecast          # now through the next 24 hours

Outputs in outputs/<run>/: scores.csv, alerts.json, map.html, plus rain.csv and
run.json so a run can be re-scored in seconds when a field report arrives
(rescore()), without downloading the rain again.
"""
import argparse
import json

import pandas as pd

from . import config
from .alerts import LANGS, template_alert, write_alerts
from .mapviz import build_map
from .rainfall import hourly_rain
from .reports import load_reports
from .score import score_frame
from .wards import load_wards


def frame_times(mode: str, replay_date: str | None) -> list[pd.Timestamp]:
    if mode == "replay":
        # From noon the day before, 48 hours — before, during and after the rain
        start = pd.Timestamp(replay_date or config.DEFAULT_REPLAY_DATE) - pd.Timedelta(hours=12)
        return list(pd.date_range(start, periods=48, freq="h"))
    start = pd.Timestamp.now(tz=config.TIMEZONE).tz_localize(None).floor("h")
    return list(pd.date_range(start, periods=24, freq="h"))


def run_name_for(mode: str, replay_date: str | None) -> str:
    return f"replay_{replay_date or config.DEFAULT_REPLAY_DATE}" if mode == "replay" else "forecast"


def run(mode: str = "replay", replay_date: str | None = None, use_llm: bool = True) -> dict:
    wards = load_wards()
    print(f"✓ loaded {len(wards)} wards")
    rain = hourly_rain(wards, mode=mode, replay_date=replay_date)
    print(f"✓ rain: {rain.index.min()} → {rain.index.max()}")

    out = config.OUTPUT_DIR / run_name_for(mode, replay_date)
    out.mkdir(parents=True, exist_ok=True)
    rain.to_csv(out / "rain.csv")
    times = frame_times(mode, replay_date)
    (out / "run.json").write_text(json.dumps({
        "mode": mode, "date": replay_date or config.DEFAULT_REPLAY_DATE,
        "frames": [t.isoformat() for t in times],
    }), encoding="utf-8")
    return score_and_write(out, wards, rain, times, mode, replay_date, use_llm)


def rescore(run_name: str, use_llm: bool = False) -> dict:
    """Re-score a saved run with the current reports (e.g. right after a photo report)."""
    out = config.OUTPUT_DIR / run_name
    meta = json.loads((out / "run.json").read_text(encoding="utf-8"))
    rain = pd.read_csv(out / "rain.csv", index_col=0, parse_dates=True)
    times = [pd.Timestamp(t) for t in meta["frames"]]
    date = meta["date"] if meta["mode"] == "replay" else None
    return score_and_write(out, load_wards(), rain, times, meta["mode"], date, use_llm, quiet=True)


def score_and_write(out, wards, rain, times, mode, replay_date, use_llm, quiet=False) -> dict:
    reports = load_reports()
    frames = pd.concat([score_frame(wards, rain, reports, t) for t in times], ignore_index=True)
    frames.to_csv(out / "scores.csv", index=False, encoding="utf-8-sig")

    # At the worst moment, which wards get which alert
    peak_t = frames.groupby("as_of")["score"].mean().idxmax()
    peak = frames[frames["as_of"] == peak_t]
    alert_rows = [r for r in peak.to_dict("records") if r["level"] != "green"]
    if use_llm:
        messages, source = write_alerts(alert_rows)
    else:
        messages, source = [{lang: template_alert(r, lang) for lang in LANGS} for r in alert_rows], "template"
    alerts = [
        {"ward_id": r["ward_id"], "name_bn": r["name_bn"], "name_en": r["name_en"], "level": r["level"],
         "score": float(r["score"]), "message_bn": m["bn"], "message_en": m["en"]}
        for r, m in zip(alert_rows, messages)
    ]
    (out / "alerts.json").write_text(
        json.dumps({"as_of": str(peak_t), "source": source, "alerts": alerts}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    date = replay_date or config.DEFAULT_REPLAY_DATE
    title = ({"bn": f"রিপ্লে · {date}", "en": f"Replay · {date}"} if mode == "replay"
             else {"bn": "লাইভ পূর্বাভাস", "en": "Live forecast"})
    build_map(wards, frames, title, out / "map.html")

    counts = peak["level"].value_counts().to_dict()
    if not quiet:
        print(f"✓ {len(alerts)} alerts ({source})")
        print(f"✓ peak risk at {peak_t}: {counts}")
        print(f"✓ output → {out}")
    return {"out": out, "peak_time": peak_t, "counts": counts}


def main():
    ap = argparse.ArgumentParser(description="Jolrekha pipeline")
    ap.add_argument("--mode", choices=["replay", "forecast"], default="replay")
    ap.add_argument("--date", help="replay date, YYYY-MM-DD")
    ap.add_argument("--no-llm", action="store_true", help="templates only, no Muse Spark")
    args = ap.parse_args()
    run(args.mode, args.date, use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
