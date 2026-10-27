"""Field reports (W): people send photos of water, depth = none/ankle/knee/waist.

Later SAM 3.1 checks the photo and sets `verified=True`; unverified reports
count for less. Reports decay over time (half-life) as water drains.
"""
import json
from datetime import datetime

import pandas as pd

from . import config


def load_reports(path=config.REPORTS_JSON) -> pd.DataFrame:
    cols = ["ward_id", "depth", "time", "verified", "source"]
    if not path.exists():
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(json.loads(path.read_text(encoding="utf-8")), columns=cols)
    df["ward_id"] = df["ward_id"].astype(str)
    df["time"] = pd.to_datetime(df["time"])
    df["verified"] = df["verified"].fillna(False).astype(bool)
    return df


def add_report(ward_id: str, depth: str, time: datetime | None = None,
               verified: bool = False, source: str = "manual", path=config.REPORTS_JSON) -> dict:
    if depth not in config.DEPTH_LEVELS:
        raise ValueError(f"depth must be one of {list(config.DEPTH_LEVELS)}")
    reports = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    rec = {
        "ward_id": str(ward_id),
        "depth": depth,
        "time": (time or datetime.now()).isoformat(timespec="minutes"),
        "verified": verified,
        "source": source,
    }
    reports.append(rec)
    path.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    return rec


def water_factor(reports: pd.DataFrame, ward_ids: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    """W ∈ [0, 1] per ward — the strongest report up to as_of."""
    w = pd.Series(0.0, index=ward_ids.values)
    if reports.empty:
        return w
    past = reports[reports["time"] <= as_of]
    if past.empty:
        return w
    age_h = (as_of - past["time"]).dt.total_seconds() / 3600
    strength = (
        past["depth"].map(config.DEPTH_LEVELS)
        * past["verified"].map({True: 1.0, False: config.UNVERIFIED_WEIGHT})
        * 0.5 ** (age_h / config.REPORT_HALF_LIFE_HOURS)
    )
    best = strength.groupby(past["ward_id"]).max()
    w.update(best)
    return w.clip(0, 1)


def strongest_depth(reports: pd.DataFrame, ward_ids: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    """Deepest report ("knee" etc.) within the last 2 half-lives, else None."""
    out = pd.Series(None, index=ward_ids.values, dtype=object)
    if reports.empty:
        return out
    window = pd.Timedelta(hours=2 * config.REPORT_HALF_LIFE_HOURS)
    recent = reports[(reports["time"] <= as_of) & (reports["time"] > as_of - window)]
    if recent.empty:
        return out
    rank = recent["depth"].map(config.DEPTH_LEVELS)
    deepest = recent.loc[rank.groupby(recent["ward_id"]).idxmax(), ["ward_id", "depth"]]
    out.update(deepest.set_index("ward_id")["depth"])
    return out
