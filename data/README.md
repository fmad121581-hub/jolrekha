# Data formats

`wards.geojson` and `informality.csv` are built by `scripts/import_classifier.py` from the classifier repo's
`data/processed/ward_predictions_extended.gpkg` (`GID_4` → `ward_id`, `prob_informal` → `p_informal`).
Rerun the import script whenever the classifier is rerun.

## Ward boundaries: GeoJSON (any CRS; the code reprojects to 4326)
Each feature's properties need:
- `ward_id`: string, must match the informality CSV
- `name_bn`: Bangla name, e.g. "ওয়ার্ড ৪৪, মোহাম্মদপুর" (shown to residents)
- `name_en`: English name as "<unit>, <thana>", e.g. "Ward No-44, Mohammadpur"

## Informality: CSV
```
ward_id,p_informal
W001,0.73
```
The classifier's probability, 0–1.

## propensity.csv: optional, built by `scripts/make_propensity.py` (DEM + MNDWI now, NISAR later)
```
ward_id,propensity
W001,0.41
```
How readily water pools in the ward, 0–1. When the file exists, V = √(p_informal × propensity).

## reports.json: field reports (written by the bot)
```json
[{"ward_id": "W001", "depth": "knee", "time": "2024-05-27T06:30", "verified": true, "source": "telegram"}]
```
`depth` is one of `none` / `ankle` / `knee` / `waist`.

Files under `sample/` are synthetic, for running the pipeline only.
