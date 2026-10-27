"""Build synthetic sample data — for running the pipeline without the real classifier output.

203 grid cells over Dhaka = "sample wards". p_informal is synthetic: higher
near a few well-known informal settlements (Korail, Kamrangirchar, Bhashantek,
Kalyanpur, Old Dhaka). For pipeline testing only — not for analysis.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jolrekha import config  # noqa: E402

N_WARDS = 203
LAT_MIN, LAT_MAX = 23.69, 23.90
LON_MIN, LON_MAX = 90.34, 90.46
ROWS, COLS = 15, 14  # 210 cells, the first 203 are used

HOTSPOTS = [  # (lat, lon, strength)
    (23.785, 90.410, 0.55),  # Korail
    (23.720, 90.370, 0.50),  # Kamrangirchar
    (23.825, 90.390, 0.40),  # Bhashantek
    (23.780, 90.360, 0.35),  # Kalyanpur
    (23.705, 90.420, 0.30),  # Sadarghat / Old Dhaka
]

BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def main():
    rng = np.random.default_rng(42)
    dlat = (LAT_MAX - LAT_MIN) / ROWS
    dlon = (LON_MAX - LON_MIN) / COLS

    features, rows = [], []
    i = 0
    for r in range(ROWS):
        for c in range(COLS):
            if i >= N_WARDS:
                break
            i += 1
            lat0, lon0 = LAT_MIN + r * dlat, LON_MIN + c * dlon
            clat, clon = lat0 + dlat / 2, lon0 + dlon / 2
            ward_id = f"W{i:03d}"

            p = 0.08
            for hlat, hlon, w in HOTSPOTS:
                d2 = ((clat - hlat) / 0.02) ** 2 + ((clon - hlon) / 0.02) ** 2
                p += w * np.exp(-d2)
            p = float(np.clip(p + rng.normal(0, 0.05), 0.01, 0.99))

            features.append({
                "type": "Feature",
                "properties": {
                    "ward_id": ward_id,
                    "name_bn": f"নমুনা ওয়ার্ড {str(i).translate(BN_DIGITS)}",
                    "name_en": f"Sample Ward {i}, Sample",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [round(lon0, 5), round(lat0, 5)],
                        [round(lon0 + dlon, 5), round(lat0, 5)],
                        [round(lon0 + dlon, 5), round(lat0 + dlat, 5)],
                        [round(lon0, 5), round(lat0 + dlat, 5)],
                        [round(lon0, 5), round(lat0, 5)],
                    ]],
                },
            })
            rows.append({"ward_id": ward_id, "p_informal": round(p, 4)})

    out = config.DATA_DIR / "sample"
    out.mkdir(parents=True, exist_ok=True)
    (out / "wards_sample.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    pd.DataFrame(rows).to_csv(out / "informality_sample.csv", index=False)
    print(f"✓ {len(rows)} sample wards → {out}")


if __name__ == "__main__":
    main()
