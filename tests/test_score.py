import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from jolrekha import config  # noqa: E402
from jolrekha.reports import water_factor  # noqa: E402
from jolrekha.score import score_frame  # noqa: E402

T0 = pd.Timestamp("2024-05-27 00:00")


def _wards():
    return pd.DataFrame({
        "ward_id": ["A", "B"], "name_bn": ["ক", "খ"], "name_en": ["A", "B"],
        "p_informal": [0.9, 0.1], "V": [0.9, 0.1],
    })


def _rain(mm_per_hour):
    idx = pd.date_range(T0 - pd.Timedelta(hours=12), periods=48, freq="h")
    return pd.DataFrame({"A": mm_per_hour, "B": mm_per_hour}, index=idx)


def _no_reports():
    return pd.DataFrame(columns=["ward_id", "depth", "time", "verified", "source"])


def test_no_rain_means_green():
    df = score_frame(_wards(), _rain(0.0), _no_reports(), T0)
    assert (df["score"] == 0).all()
    assert (df["level"] == "green").all()


def test_heavy_rain_without_reports_still_alerts():
    # No reports must not zero the score — that's the core design
    df = score_frame(_wards(), _rain(5.0), _no_reports(), T0).set_index("ward_id")
    assert df.loc["A", "score"] > 0
    assert df.loc["A", "level"] == "red"


def test_vulnerable_ward_ranks_first():
    df = score_frame(_wards(), _rain(1.5), _no_reports(), T0)
    assert df.iloc[0]["ward_id"] == "A"
    assert df.iloc[0]["score"] > df.iloc[1]["score"] > 0


def test_report_raises_score_and_decays():
    reports = pd.DataFrame([{"ward_id": "B", "depth": "knee", "time": T0,
                             "verified": True, "source": "test"}])
    base = score_frame(_wards(), _rain(1.0), _no_reports(), T0).set_index("ward_id")
    boosted = score_frame(_wards(), _rain(1.0), reports, T0).set_index("ward_id")
    assert boosted.loc["B", "score"] > base.loc["B", "score"]
    assert boosted.loc["B", "report_depth"] == "knee"

    ids = pd.Series(["B"])
    now = water_factor(reports, ids, T0)["B"]
    later = water_factor(reports, ids, T0 + pd.Timedelta(hours=config.REPORT_HALF_LIFE_HOURS))["B"]
    assert abs(later - now / 2) < 1e-9


def test_future_reports_ignored():
    reports = pd.DataFrame([{"ward_id": "A", "depth": "waist", "time": T0 + pd.Timedelta(hours=1),
                             "verified": True, "source": "test"}])
    assert water_factor(reports, pd.Series(["A"]), T0)["A"] == 0
