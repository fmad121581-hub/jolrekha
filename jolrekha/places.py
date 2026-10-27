"""Place name → wards. Handles Bangla, English and Banglish spellings plus small typos.

    find_wards("মোহাম্মদপুরে আজ পানি উঠবে?")  → [ward_id, ...]
    find_wards("ward 44")                       → the ward with old DCC number 44

Ward numbers are GADM's (old Dhaka City Corporation), not today's DNCC/DSCC numbers.
The Bangla aliases below are data, not UI text — they must stay in Bangla.
"""
import re
from difflib import SequenceMatcher
from functools import lru_cache

import geopandas as gpd

BN_TO_ASCII = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
WARD_NO_RE = re.compile(r"(?:ward|ওয়ার্ড|ওয়ার্ড|ওয়াড)\s*(?:no\.?|নং|নম্বর)?\s*[-:]?\s*(\d{1,3})", re.IGNORECASE)

# Well-known neighbourhoods → thanas (English GADM names). Extend as needed.
NEIGHBOURHOODS = {
    "পুরান ঢাকা": ["Kotwali", "Sutrapur", "Lalbagh", "Bangshal", "Chak Bazar", "Gendaria"],
    "পুরনো ঢাকা": ["Kotwali", "Sutrapur", "Lalbagh", "Bangshal", "Chak Bazar", "Gendaria"],
    "old dhaka": ["Kotwali", "Sutrapur", "Lalbagh", "Bangshal", "Chak Bazar", "Gendaria"],
    "puran dhaka": ["Kotwali", "Sutrapur", "Lalbagh", "Bangshal", "Chak Bazar", "Gendaria"],
    "সদরঘাট": ["Kotwali"], "sadarghat": ["Kotwali"],
    "আজিমপুর": ["Lalbagh"], "azimpur": ["Lalbagh"],
    "বনানী": ["Gulshan"], "banani": ["Gulshan"],
    "কড়াইল": ["Gulshan"], "korail": ["Gulshan"],
    "ফার্মগেট": ["Tejgaon"], "farmgate": ["Tejgaon"],
    "কারওয়ান বাজার": ["Tejgaon"], "karwan bazar": ["Tejgaon"], "kawran bazar": ["Tejgaon"],
}

# Common alternative Banglish spellings
SPELLING = [("ganj", "gonj"), ("gaon", "gao"), ("bagh", "bag"),
            ("mohammad", "mohammod"), ("mohammad", "muhammad"), ("char", "chor"),
            ("nawab", "nabab"), ("gendaria", "gandaria")]

# Collapse common Bangla spelling variants (applied to both sides): যাত্রাবারি = যাত্রাবাড়ী
BN_PHONETIC = [("ড়", "র"), ("ড়", "র"), ("ঢ়", "র"), ("ঢ়", "র"), ("য়", "য"), ("য়", "য"),
               ("ী", "ি"), ("ূ", "ু"), ("ণ", "ন"), ("ষ", "স"), ("শ", "স"), ("ৎ", "ত"), ("ঁ", "")]


def _norm(s: str) -> str:
    s = s.translate(BN_TO_ASCII).lower()
    for a, b in BN_PHONETIC:
        s = s.replace(a, b)
    s = re.sub(r"[^\w\sঀ-৿]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _variants(name_en: str) -> set[str]:
    base = _norm(name_en)
    out = {base, base.replace(" ", ""), base.replace("-", " ")}
    for a, b in SPELLING:
        out |= {v.replace(a, b) for v in list(out)}
    return out


def _build_index(wards: gpd.GeoDataFrame):
    """alias → {ward_id}, old DCC ward number → {ward_id}."""
    alias: dict[str, set[str]] = {}
    ward_no: dict[int, set[str]] = {}
    thana_of: dict[str, str] = {}

    def add(key, wid):
        key = _norm(key)
        if len(key) >= 3:
            alias.setdefault(key, set()).add(wid)

    for _, w in wards.iterrows():
        wid = w["ward_id"]
        unit_en, thana_en = [p.strip() for p in w["name_en"].rsplit(",", 1)]
        unit_bn, _, thana_bn = w["name_bn"].rpartition(", ")
        thana_of[wid] = thana_en
        for v in _variants(thana_en):
            add(v, wid)
        add(thana_bn or w["name_bn"], wid)
        m = WARD_NO_RE.search(unit_en)
        if m:
            ward_no.setdefault(int(m.group(1)), set()).add(wid)
        else:
            unit_clean = re.sub(r"\(part\)", "", unit_en, flags=re.IGNORECASE)
            for v in _variants(unit_clean):
                add(v, wid)
            if unit_bn and not WARD_NO_RE.search(unit_bn):
                add(re.sub(r"\(আংশিক\)", "", unit_bn), wid)

    by_thana: dict[str, set[str]] = {}
    for wid, t in thana_of.items():
        by_thana.setdefault(t, set()).add(wid)
    for name, thanas in NEIGHBOURHOODS.items():
        for t in thanas:
            for wid in by_thana.get(t, ()):
                add(name, wid)
    return alias, ward_no


@lru_cache(maxsize=1)
def _wards() -> gpd.GeoDataFrame:
    from .wards import load_wards  # slow to load, so only on first use
    return load_wards()


@lru_cache(maxsize=1)
def index():
    return _build_index(_wards())


def ward_at(lat: float, lon: float) -> str | None:
    """Ward containing a point (e.g. a location shared in Telegram), or None outside the district."""
    from shapely.geometry import Point

    w = _wards()
    hit = w[w.geometry.contains(Point(lon, lat))]
    return hit["ward_id"].iloc[0] if len(hit) else None


def ward_names(ward_id: str) -> dict:
    row = _wards().set_index("ward_id").loc[ward_id]
    return {"bn": row["name_bn"], "en": row["name_en"]}


def find_wards(query: str, fuzzy_cutoff: float = 0.82) -> list[str]:
    alias, ward_no = index()
    q = _norm(query)

    hits: set[str] = set()
    # 1. Exact names (longest alias first, so "পুরান ঢাকা" wins over shorter ones)
    for key in sorted(alias, key=len, reverse=True):
        if re.search(rf"(?<![\wঀ-৿]){re.escape(key)}", q):
            hits |= alias[key]
            q = q.replace(key, " ")
    # 2. Typos: compare each word and word pair against the aliases
    if not hits:
        words = q.split()
        grams = words + [" ".join(p) for p in zip(words, words[1:])]
        for g in grams:
            for key in alias:
                if abs(len(g) - len(key)) <= 3 and SequenceMatcher(None, g, key).ratio() >= fuzzy_cutoff:
                    hits |= alias[key]
                # Bangla case endings: "মোহাম্মদপুরে", "মিরপুরের"
                elif g.startswith(key) and len(g) - len(key) <= 3:
                    hits |= alias[key]
    # 3. Ward number — restricted to the named area if a name was found
    m = WARD_NO_RE.search(query.translate(BN_TO_ASCII))
    if m:
        numbered = ward_no.get(int(m.group(1)), set())
        hits = ((hits & numbered) or numbered) if hits else numbered
    return sorted(hits)
