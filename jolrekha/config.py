"""Jolrekha — every tunable number in one place."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"

# --- Inputs ---
# Built by scripts/import_classifier.py from the classifier's GeoPackage
# (to go back to synthetic data: DATA_DIR / "sample" / "wards_sample.geojson" etc.)
WARDS_GEOJSON = DATA_DIR / "wards.geojson"
INFORMALITY_CSV = DATA_DIR / "informality.csv"
# Optional: waterlogging propensity (ward_id, propensity 0–1), see scripts/make_propensity.py
PROPENSITY_CSV = DATA_DIR / "propensity.csv"
REPORTS_JSON = DATA_DIR / "reports.json"

TIMEZONE = "Asia/Dhaka"

# --- Rain (R) ---
# BMD classes: 44–88 mm/24h "heavy", ≥89 "very heavy"
RAIN_24H_FULL_MM = 89.0
# Above this per hour Dhaka's drains usually can't keep up (assumption, tune it)
RAIN_1H_FULL_MM = 30.0
# Recent rain counts too — water takes time to drain
LOOKBACK_HOURS = 6
LOOKAHEAD_HOURS = 12   # 6h back + 12h ahead = 18h window, compared to the 24h threshold (conservative)

# --- Vulnerability (V) ---
# score = R × (V_FLOOR + (1 − V_FLOOR)·V) × (1 + W)
# V_FLOOR > 0 so low-vulnerability wards still register under very heavy rain
V_FLOOR = 0.4

# --- Field reports (W) ---
DEPTH_LEVELS = {"none": 0.0, "ankle": 0.33, "knee": 0.66, "waist": 1.0}
REPORT_HALF_LIFE_HOURS = 3.0
UNVERIFIED_WEIGHT = 0.5   # half weight until SAM verifies the photo

# --- Alert levels (score ≥ threshold) ---
ALERT_LEVELS = [
    ("red", 0.60),
    ("orange", 0.40),
    ("yellow", 0.20),
    ("green", 0.0),
]

# Replay demo: Cyclone Remal, ~175 mm in Dhaka (Open-Meteo archive)
DEFAULT_REPLAY_DATE = "2024-05-27"
