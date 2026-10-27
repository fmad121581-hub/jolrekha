"""Check the waterlogging layers against a real Dhaka flood seen by Sentinel-1.

    python scripts/validate_propensity_sar.py

Event: 21 Sep 2023 Dhaka flood. Scenes from the NISAR repo
(D:\\NISAR_Dhaka_Flood\\processed\\dhaka_sep2023_case): S1A 2023-09-10 (pre) and
2023-09-22 (during/after), descending, coregistered, Δσ⁰ = during − pre in dB.

Per ward we take the fraction of pixels that darkened by ≥ 3 dB (open water is a
specular, dark reflector) and correlate it (Spearman) with propensity, informality
and V. Caveat — and it is a big one: the NISAR repo's own pixel-level validation of
this scene found kappa ≈ 0.01 against the hazard map, because C-band SAR misses
water between buildings (double-bounce) and the 22 Sep pass came after much of
the water had drained. Treat this as a weak, partial check, not ground truth.
"""
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterstats import zonal_stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jolrekha import config  # noqa: E402
from jolrekha.wards import load_wards  # noqa: E402

DELTA = Path(r"D:\NISAR_Dhaka_Flood\processed\dhaka_sep2023_case\coregistered\delta_s1_sep22_minus_sep10.tif")
DARKEN_DB = -3.0
MIN_PIXELS = 200  # ~0.18 km² at 30 m; smaller samples are too noisy


def main():
    wards = load_wards()
    with rasterio.open(DELTA) as src:
        arr = src.read(1).astype("float32")
        arr[arr == src.nodata] = np.nan
        geoms = wards.to_crs(src.crs).geometry
        dark = np.where(np.isnan(arr), np.nan, (arr <= DARKEN_DB).astype("float32"))
        frac = zonal_stats(geoms, dark, affine=src.transform, stats=["mean", "count"], nodata=np.nan)

    df = pd.DataFrame({
        "ward_id": wards["ward_id"], "name": wards["name_en"],
        "is_city_ward": wards["name_en"].str.contains("Ward No", case=False),
        "p_informal": wards["p_informal"], "propensity": wards["propensity"].astype(float), "V": wards["V"],
        "sar_dark_frac": [s["mean"] for s in frac], "sar_pixels": [s["count"] for s in frac],
    })
    df = df[df["sar_pixels"] >= MIN_PIXELS].dropna(subset=["sar_dark_frac"])

    rows = []
    for subset, d in [("all units", df), ("city wards only", df[df["is_city_ward"]])]:
        for col in ["propensity", "p_informal", "V"]:
            rho = d[col].corr(d["sar_dark_frac"], method="spearman")
            rows.append({"subset": subset, "n": len(d), "layer": col, "spearman_vs_sar": round(rho, 3)})
    res = pd.DataFrame(rows)

    out_dir = config.DATA_DIR / "validation"
    out_dir.mkdir(exist_ok=True)
    df.to_csv(out_dir / "sar_sep2023_by_ward.csv", index=False)
    res.to_csv(out_dir / "sar_sep2023_spearman.csv", index=False)
    print(res.to_string(index=False))
    print(f"\nTop SAR-darkened wards:\n{df.sort_values('sar_dark_frac', ascending=False).head(8)[['name', 'sar_dark_frac', 'propensity']].round(3).to_string(index=False)}")
    print(f"\n✓ wrote {out_dir}")


if __name__ == "__main__":
    main()
