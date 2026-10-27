"""Waterlogging propensity — from the classifier repo's DEM and Sentinel-2 MNDWI.

    python scripts/make_propensity.py

Three components, each a percentile rank (0–1) across the 203 units:
  low      how low the ward's median elevation is        — water drains to low ground
  hollow   how much lower it is than a 2 km ring around it — water runs in from around (urban waterlogging)
  wet      how high s2_mndwi_mean is                      — more water bodies / wet soil

Using "low" alone puts the Dohar–Nawabganj floodplain on top, which is river
flooding. "hollow" captures urban waterlogging better, so it gets the most weight.

Limitations: SRTM C-band reads dense built-up areas a bit high (it's a DSM),
and the weights are a judgement call — still to be validated against NISAR's
historical inundation maps.
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

CLASSIFIER = Path(r"C:\Users\user\OneDrive\Projects\informal-settlement-classifier\data\processed")
DEM = CLASSIFIER / "dem_utm46n.tif"
PREDICTIONS = CLASSIFIER / "ward_predictions_extended.gpkg"

RING_M = 2000
WEIGHTS = {"low": 0.35, "hollow": 0.45, "wet": 0.20}
DEM_MIN_VALID = -5  # SRTM artefacts below this


def _dem_median(geoms, dem_path) -> np.ndarray:
    with rasterio.open(dem_path) as src:
        arr = src.read(1).astype("float32")
        arr[(arr == src.nodata) | (arr < DEM_MIN_VALID)] = np.nan
        stats = zonal_stats(geoms, arr, affine=src.transform, stats=["median", "count"], nodata=np.nan)
    return np.array([s["median"] if s["count"] else np.nan for s in stats], dtype=float)


def main():
    g = gpd.read_file(PREDICTIONS)
    with rasterio.open(DEM) as src:
        g = g.to_crs(src.crs)

    elev = _dem_median(g.geometry, DEM)
    # Surrounding ring = (ward + 2 km) − ward
    ring = g.geometry.buffer(RING_M).difference(g.geometry)
    ring_elev = _dem_median(ring, DEM)

    df = pd.DataFrame({
        "ward_id": g["GID_4"],
        "name": g["NAME_4"] + ", " + g["NAME_3"],
        "elev_median_m": elev.round(1),
        "hollow_m": (ring_elev - elev).round(2),  # positive = lower than its surroundings
        "mndwi": g["s2_mndwi_mean"],
    })
    missing = df["elev_median_m"].isna().sum()
    if missing:
        print(f"⚠ {missing} units have no DEM coverage — filled with the median")
        df["elev_median_m"] = df["elev_median_m"].fillna(df["elev_median_m"].median())
        df["hollow_m"] = df["hollow_m"].fillna(0)

    df["low"] = (-df["elev_median_m"]).rank(pct=True)
    df["hollow"] = df["hollow_m"].rank(pct=True)
    df["wet"] = df["mndwi"].rank(pct=True)
    df["propensity"] = sum(w * df[k] for k, w in WEIGHTS.items()).round(4)

    out = config.DATA_DIR / "propensity.csv"
    df.to_csv(out, index=False)
    print(f"✓ {len(df)} units → {out}")
    print(df.sort_values("propensity", ascending=False)
          [["name", "elev_median_m", "hollow_m", "mndwi", "propensity"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()
