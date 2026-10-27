"""Live map: one self-contained HTML file (Leaflet) with a time slider and a বাংলা/English switch.

Per-frame messages are rendered in the browser from the same templates as
alerts.py (passed in as data), so the file stays small and both languages
always say the same thing.
"""
import json

import pandas as pd

from . import config
from .alerts import LEVEL_NAMES, RAIN_NOTE, TEMPLATES

TEMPLATE = config.ROOT / "web" / "map_template.html"


def build_map(wards, frames: pd.DataFrame, title: dict, out_path) -> None:
    times = sorted(frames["as_of"].unique())
    by_ward = {wid: g.set_index("as_of").reindex(times) for wid, g in frames.groupby("ward_id")}

    features = []
    for _, w in wards.iterrows():
        g = by_ward[w["ward_id"]]
        features.append({
            "type": "Feature",
            "geometry": w.geometry.__geo_interface__,
            "properties": {
                "id": w["ward_id"],
                "name_bn": w["name_bn"],
                "name_en": w["name_en"],
                "p": round(float(w["p_informal"]), 2),
                "score": g["score"].round(2).tolist(),
                "level": g["level"].tolist(),
                "rain": g["rain_total"].round().astype(int).tolist(),
            },
        })

    data = {
        "title": title,
        "times": [pd.Timestamp(t).strftime("%Y-%m-%d %H:%M") for t in times],
        "levels": LEVEL_NAMES,
        "templates": TEMPLATES,
        "rain_note": RAIN_NOTE,
        "geojson": {"type": "FeatureCollection", "features": features},
    }
    html = TEMPLATE.read_text(encoding="utf-8").replace(
        "/*__DATA__*/null", json.dumps(data, ensure_ascii=False)
    )
    out_path.write_text(html, encoding="utf-8")
