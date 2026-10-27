"""Hourly rainfall from Open-Meteo — live forecast or a past day (replay).

Open-Meteo's grid is coarser than Dhaka's wards, so several wards fall in one
cell. Centroids are snapped to ~0.05° cells to cut the number of requests.
"""
from datetime import date, timedelta

import pandas as pd
import requests

from . import config

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
BATCH = 50
SNAP_DEG = 0.05


def _snap(x: float) -> float:
    return round(round(x / SNAP_DEG) * SNAP_DEG, 3)


def _fetch(url: str, points: list[tuple[float, float]], extra: dict) -> list[pd.Series]:
    series = []
    for i in range(0, len(points), BATCH):
        chunk = points[i:i + BATCH]
        params = {
            "latitude": ",".join(str(p[0]) for p in chunk),
            "longitude": ",".join(str(p[1]) for p in chunk),
            "hourly": "precipitation",
            "timezone": config.TIMEZONE,
            **extra,
        }
        resp = requests.get(url, params=params, timeout=60)
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, dict):  # a single point comes back as a dict, not a list
            payload = [payload]
        for item in payload:
            h = item["hourly"]
            series.append(pd.Series(h["precipitation"], index=pd.to_datetime(h["time"]), dtype=float))
    return series


def hourly_rain(wards: pd.DataFrame, mode: str = "forecast", replay_date: str | None = None) -> pd.DataFrame:
    """Returns index = hour (Dhaka time), columns = ward_id, values = mm."""
    snapped = list(zip(wards["lat"].map(_snap), wards["lon"].map(_snap)))
    cells = sorted(set(snapped))

    if mode == "forecast":
        extra = {"past_days": 1, "forecast_days": 3}
        url = FORECAST_URL
    elif mode == "replay":
        d = date.fromisoformat(replay_date or config.DEFAULT_REPLAY_DATE)
        extra = {
            "start_date": (d - timedelta(days=1)).isoformat(),
            "end_date": (d + timedelta(days=1)).isoformat(),
        }
        url = ARCHIVE_URL
    else:
        raise ValueError(f"unknown mode: {mode}")

    cell_series = dict(zip(cells, _fetch(url, cells, extra)))
    rain = pd.DataFrame({wid: cell_series[c] for wid, c in zip(wards["ward_id"], snapped)})
    return rain.fillna(0.0)
