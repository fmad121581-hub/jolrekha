"""Scoring engine.

    score = min(1, R × (V_FLOOR + (1 − V_FLOOR)·V) × (1 + W))

R = rain (forecast + recent), V = ward vulnerability, W = field reports.
With no reports W = 0 and the score is not zero — so alerts go out *before* the rain.
"""
import pandas as pd

from . import config
from .reports import strongest_depth, water_factor


def rain_factor(rain: pd.DataFrame, as_of: pd.Timestamp) -> pd.DataFrame:
    """Per ward: rain_total, rain_peak (mm) and R ∈ [0, 1]."""
    start = as_of - pd.Timedelta(hours=config.LOOKBACK_HOURS)
    end = as_of + pd.Timedelta(hours=config.LOOKAHEAD_HOURS)
    window = rain[(rain.index >= start) & (rain.index < end)]
    total = window.sum()
    peak = window.max().fillna(0.0)
    r = pd.concat([total / config.RAIN_24H_FULL_MM, peak / config.RAIN_1H_FULL_MM], axis=1).max(axis=1)
    return pd.DataFrame({"rain_total": total.round(1), "rain_peak": peak.round(1), "R": r.clip(0, 1)})


def alert_level(score: float) -> str:
    for name, threshold in config.ALERT_LEVELS:
        if score >= threshold:
            return name
    return "green"


def score_frame(wards: pd.DataFrame, rain: pd.DataFrame, reports: pd.DataFrame,
                as_of: pd.Timestamp) -> pd.DataFrame:
    """Scores for every ward at one moment (as_of), highest risk first."""
    df = wards[["ward_id", "name_bn", "name_en", "p_informal", "V"]].set_index("ward_id")
    df = df.join(rain_factor(rain, as_of))
    df["W"] = water_factor(reports, df.index.to_series(), as_of)
    df["report_depth"] = strongest_depth(reports, df.index.to_series(), as_of)
    v_term = config.V_FLOOR + (1 - config.V_FLOOR) * df["V"]
    df["score"] = (df["R"] * v_term * (1 + df["W"])).clip(upper=1).round(3)
    df["level"] = df["score"].map(alert_level)
    df["as_of"] = as_of
    return df.reset_index().sort_values("score", ascending=False, ignore_index=True)
