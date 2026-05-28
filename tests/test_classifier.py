"""Tests for tidycop.classifier (SpotCrime 8-category mapping)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from tidycop import get_incidents
from tidycop.classifier import (
    SPOTCRIME_CATEGORIES,
    classify_frame,
    classify_row,
)
from tidycop.registry import _reset_cache, get_city_spec
from tidycop.schema import STD_COLUMNS

# ---------------------------------------------------------------------------
# Constants / sanity
# ---------------------------------------------------------------------------


def test_eight_canonical_categories():
    # Homicide was removed 2026-05-26 — fatal shootings collapse into Shooting.
    assert "Homicide" not in SPOTCRIME_CATEGORIES
    assert "Shooting" in SPOTCRIME_CATEGORIES
    assert len(SPOTCRIME_CATEGORIES) == 8
    assert set(SPOTCRIME_CATEGORIES) == {
        "Shooting",
        "Robbery",
        "Assault",
        "Burglary",
        "Theft",
        "Arson",
        "Vandalism",
        "Arrest",
    }


# ---------------------------------------------------------------------------
# classify_row
# ---------------------------------------------------------------------------


CHI_MAP = {
    "THEFT": "Theft",
    "ROBBERY": "Robbery",
    "BURGLARY": "Burglary",
    "ARSON": "Arson",
    "BATTERY": "Assault",
}


def test_classify_row_hits_offense_category():
    assert classify_row({"std_offense_category": "THEFT"}, CHI_MAP) == "Theft"


def test_classify_row_falls_back_to_description():
    row = {"std_offense_category": None, "std_offense_description": "Robbery"}
    assert classify_row(row, CHI_MAP) == "Robbery"


def test_classify_row_case_insensitive():
    assert classify_row({"std_offense_category": "theft"}, CHI_MAP) == "Theft"
    assert classify_row({"std_offense_category": "  Theft  "}, CHI_MAP) == "Theft"


def test_classify_row_unmapped_returns_none():
    assert classify_row({"std_offense_category": "KIDNAPPING"}, CHI_MAP) is None


def test_classify_row_handles_missing_fields():
    assert classify_row({}, CHI_MAP) is None
    assert classify_row({"std_offense_category": None}, CHI_MAP) is None
    assert classify_row({"std_offense_category": ""}, CHI_MAP) is None


def test_classify_row_works_on_pandas_series():
    s = pd.Series({"std_offense_category": "ARSON"})
    assert classify_row(s, CHI_MAP) == "Arson"


# ---------------------------------------------------------------------------
# classify_frame
# ---------------------------------------------------------------------------


def _frame(categories: list[str]) -> pd.DataFrame:
    rows = []
    for c in categories:
        rec = {col: None for col in STD_COLUMNS}
        rec["std_offense_category"] = c
        rows.append(rec)
    return pd.DataFrame(rows, columns=STD_COLUMNS)


def test_classify_frame_adds_column():
    df = _frame(["THEFT", "ROBBERY", "KIDNAPPING"])
    out = classify_frame(df, CHI_MAP)
    assert "std_spotcrime_category" in out.columns
    assert list(out["std_spotcrime_category"]) == ["Theft", "Robbery", None]


def test_classify_frame_empty_mapping_returns_null_column():
    df = _frame(["THEFT", "ROBBERY"])
    out = classify_frame(df, None)
    assert "std_spotcrime_category" in out.columns
    assert out["std_spotcrime_category"].isna().all()


def test_classify_frame_rejects_invalid_categories():
    with pytest.raises(ValueError, match="invalid target categories"):
        classify_frame(_frame(["THEFT"]), {"THEFT": "Petty Larceny"})


def test_classify_frame_handles_empty_dataframe():
    df = pd.DataFrame(columns=STD_COLUMNS)
    out = classify_frame(df, CHI_MAP)
    assert "std_spotcrime_category" in out.columns
    assert len(out) == 0


# ---------------------------------------------------------------------------
# Registry coverage: 5 MVP cities ship a SpotCrime map
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("city", ["chicago", "seattle", "san_francisco", "detroit", "pittsburgh"])
def test_mvp_cities_have_spotcrime_map(city: str):
    _reset_cache()
    spec = get_city_spec(city)
    src = spec.sources[0]
    assert src.spotcrime_category_map, f"{city}: missing spotcrime_category_map"
    # All targets must be in the 8 valid categories.
    for native, target in src.spotcrime_category_map.items():
        assert target in SPOTCRIME_CATEGORIES, f"{city}: {native!r} maps to invalid {target!r}"


def test_mvp_cities_cover_core_buckets():
    """Every MVP city should at least cover Theft, Robbery, Assault, Burglary."""
    _reset_cache()
    required = {"Theft", "Robbery", "Assault", "Burglary"}
    for city in ("chicago", "seattle", "san_francisco", "detroit", "pittsburgh"):
        spec = get_city_spec(city)
        covered = set(spec.sources[0].spotcrime_category_map.values())
        missing = required - covered
        assert not missing, f"{city}: missing core buckets {missing}"


# ---------------------------------------------------------------------------
# get_incidents() integration
# ---------------------------------------------------------------------------


class _StubFetcher:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self, source, start_date, end_date, *, limit=1000):
        return list(self.rows)


def _chicago_raw(primary_types):
    return [
        {
            "id": f"id{i}",
            "case_number": f"JZ{i:05d}",
            "date": "2026-04-01T12:00:00.000",
            "iucr": "0820",
            # description is intentionally a non-mappable label so the
            # fallback path in classify_row doesn't accidentally rescue
            # categories the test wants to be unmapped.
            "description": "GENERIC OFFENSE",
            "primary_type": pt,
            "block": "001XX N STATE ST",
            "community_area": "8",
            "district": "001",
            "beat": "0111",
            "latitude": "41.0",
            "longitude": "-87.0",
        }
        for i, pt in enumerate(primary_types)
    ]


def test_get_incidents_classify_spotcrime_off_by_default():
    fetcher = _StubFetcher(_chicago_raw(["THEFT", "BATTERY"]))
    df = get_incidents("chicago", date(2026, 4, 1), date(2026, 4, 1), fetcher=fetcher)
    assert "std_spotcrime_category" not in df.columns


def test_get_incidents_classify_spotcrime_on():
    fetcher = _StubFetcher(_chicago_raw(["THEFT", "ROBBERY", "ARSON", "KIDNAPPING"]))
    df = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        fetcher=fetcher,
        classify_spotcrime=True,
    )
    assert "std_spotcrime_category" in df.columns
    assert list(df["std_spotcrime_category"]) == ["Theft", "Robbery", "Arson", None]


def test_get_incidents_classify_fatal_shootings_collapse_to_shooting():
    """Pre-2026-05-26 we had a 'Homicide' bucket; now fatal shootings → Shooting."""
    fetcher = _StubFetcher(_chicago_raw(["HOMICIDE"]))
    df = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        fetcher=fetcher,
        classify_spotcrime=True,
    )
    assert df["std_spotcrime_category"].iat[0] == "Shooting"
