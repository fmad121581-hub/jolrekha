"""Bring the classifier's output (ward_predictions_extended.gpkg) into Jolrekha's format.

    python scripts/import_classifier.py [path/to/ward_predictions_extended.gpkg]

Units are GADM Level-4: city wards (old DCC numbers, e.g. "Ward No-44") and
rural unions. Nothing is written into the classifier repo.
"""
import re
import sys
from pathlib import Path

import geopandas as gpd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jolrekha import config  # noqa: E402

DEFAULT_GPKG = Path(
    r"C:\Users\user\OneDrive\Projects\informal-settlement-classifier"
    r"\data\processed\ward_predictions_extended.gpkg"
)
SIMPLIFY_M = 20  # keeps the map file small; not visible at city scale

# Bangla thana names — user-facing data, shown in alerts and the chatbot
THANA_BN = {
    "Adabor": "আদাবর", "Badda": "বাড্ডা", "Bangshal": "বংশাল", "Biman Bandar": "বিমানবন্দর",
    "Cantonment": "ক্যান্টনমেন্ট", "Chak Bazar": "চকবাজার", "Dakshinkhan": "দক্ষিণখান",
    "Darus Salam": "দারুস সালাম", "Demra": "ডেমরা", "Dhamrai": "ধামরাই", "Dhanmondi": "ধানমন্ডি",
    "Dohar": "দোহার", "Gendaria": "গেন্ডারিয়া", "Gulshan": "গুলশান", "Hazaribagh": "হাজারীবাগ",
    "Jatrabari": "যাত্রাবাড়ী", "Kadamtali": "কদমতলী", "Kafrul": "কাফরুল", "Kalabagan": "কলাবাগান",
    "Kamrangir Char": "কামরাঙ্গীরচর", "Keraniganj": "কেরানীগঞ্জ", "Khilgaon": "খিলগাঁও",
    "Khilkhet": "খিলক্ষেত", "Kotwali": "কোতোয়ালী", "Lalbagh": "লালবাগ", "Mirpur": "মিরপুর",
    "Mohammadpur": "মোহাম্মদপুর", "Motijheel": "মতিঝিল", "Nawabganj": "নবাবগঞ্জ",
    "New Market": "নিউ মার্কেট", "Pallabi": "পল্লবী", "Paltan": "পল্টন", "Ramna": "রমনা",
    "Rampura": "রামপুরা", "Sabujbagh": "সবুজবাগ", "Savar": "সাভার", "Shah Ali": "শাহ আলী",
    "Shahbagh": "শাহবাগ", "Sher-e-bangla Nagar": "শেরেবাংলা নগর", "Shyampur": "শ্যামপুর",
    "Sutrapur": "সূত্রাপুর", "Tejgaon": "তেজগাঁও", "Tejgaon Ind. Area": "তেজগাঁও শিল্পাঞ্চল",
    "Turag": "তুরাগ", "Uttar Khan": "উত্তরখান", "Uttara": "উত্তরা",
}
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
WARD_RE = re.compile(r"Ward\s*No\.?\s*-?\s*(\d+)\s*(\(part\))?", re.IGNORECASE)


def bangla_name(name4: str, thana: str) -> str:
    thana_bn = THANA_BN.get(thana, thana)
    m = WARD_RE.search(name4)
    if m:
        part = " (আংশিক)" if m.group(2) else ""
        return f"ওয়ার্ড {m.group(1).translate(BN_DIGITS)}{part}, {thana_bn}"
    part = " (আংশিক)" if re.search(r"\(part\)", name4, re.IGNORECASE) else ""
    base = re.sub(r"\s*\(part\)", "", name4, flags=re.IGNORECASE).strip()
    if base == thana:  # e.g. NAME_4 "Badda", NAME_3 "Badda"
        return thana_bn + part
    base = base.replace("Paurashava", "পৌরসভা")
    # Union names are still in Latin script — TODO: add verified Bangla spellings
    return f"{base}{part}, {thana_bn}"


def main(gpkg: Path = DEFAULT_GPKG):
    g = gpd.read_file(gpkg)
    missing = sorted(set(g["NAME_3"]) - set(THANA_BN))
    if missing:
        print(f"⚠ thanas without a Bangla name: {missing}")

    g["geometry"] = g.geometry.simplify(SIMPLIFY_M, preserve_topology=True)
    wards = gpd.GeoDataFrame({
        "ward_id": g["GID_4"],
        "name_bn": [bangla_name(n, t) for n, t in zip(g["NAME_4"], g["NAME_3"])],
        "name_en": g["NAME_4"] + ", " + g["NAME_3"],
        "thana": g["NAME_3"],
        "is_city_ward": g["NAME_4"].map(lambda n: bool(WARD_RE.search(n))),
    }, geometry=g.geometry, crs=g.crs).to_crs(4326)

    out_geo = config.DATA_DIR / "wards.geojson"
    out_csv = config.DATA_DIR / "informality.csv"
    if out_geo.exists():
        out_geo.unlink()  # the GeoJSON driver can't overwrite an existing file
    wards.to_file(out_geo, driver="GeoJSON")
    g[["GID_4", "prob_informal", "risk_tier", "confidence", "model_agrees"]].rename(
        columns={"GID_4": "ward_id", "prob_informal": "p_informal"}
    ).to_csv(out_csv, index=False)

    print(f"✓ {len(wards)} units ({wards['is_city_ward'].sum()} city wards) → {out_geo.name}, {out_csv.name}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_GPKG)
