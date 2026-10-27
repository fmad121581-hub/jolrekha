"""Load ward boundaries + informality probability + (optional) waterlogging propensity."""
import geopandas as gpd
import pandas as pd

from . import config


def load_wards(
    geojson=config.WARDS_GEOJSON,
    informality_csv=config.INFORMALITY_CSV,
    propensity_csv=config.PROPENSITY_CSV,
) -> gpd.GeoDataFrame:
    """One row per ward: ward_id, name_bn, name_en, p_informal, propensity, V, lat, lon, geometry."""
    gdf = gpd.read_file(geojson).to_crs(4326)
    gdf["ward_id"] = gdf["ward_id"].astype(str)

    inf = pd.read_csv(informality_csv, dtype={"ward_id": str})
    gdf = gdf.merge(inf[["ward_id", "p_informal"]], on="ward_id", how="left")
    missing = gdf["p_informal"].isna().sum()
    if missing:
        print(f"⚠ {missing} wards have no p_informal — using 0.5")
        gdf["p_informal"] = gdf["p_informal"].fillna(0.5)

    if propensity_csv and propensity_csv.exists():
        prop = pd.read_csv(propensity_csv, dtype={"ward_id": str})
        gdf = gdf.merge(prop[["ward_id", "propensity"]], on="ward_id", how="left")
        gdf["propensity"] = gdf["propensity"].fillna(gdf["propensity"].median())
    else:
        gdf["propensity"] = pd.NA

    gdf["V"] = vulnerability(gdf["p_informal"], gdf["propensity"])

    # Project to metres (UTM 46N) for centroids
    cent = gdf.to_crs(32646).geometry.centroid.to_crs(4326)
    gdf["lat"], gdf["lon"] = cent.y.round(4), cent.x.round(4)
    return gdf


def vulnerability(p_informal: pd.Series, propensity: pd.Series) -> pd.Series:
    """V = how exposed people are × how readily water pools. Informality alone if no propensity."""
    if propensity.isna().all():
        return p_informal.clip(0, 1)
    # Geometric mean; the 0.05 floor keeps one zero from zeroing out V entirely
    return ((p_informal.clip(0.05, 1) * propensity.astype(float).clip(0.05, 1)) ** 0.5).clip(0, 1)
