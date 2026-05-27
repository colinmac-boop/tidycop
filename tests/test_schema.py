"""Tests for tidycop.schema."""

from __future__ import annotations

import pandas as pd
import pytest

from tidycop.schema import STD_COLUMNS, empty_frame, normalize

# ---------------------------------------------------------------------------
# STD_COLUMNS contract
# ---------------------------------------------------------------------------


def test_std_columns_count():
    """Schema is fixed at 23 columns — matches R standardized_incidents.R."""
    assert len(STD_COLUMNS) == 23


def test_std_columns_unique():
    assert len(set(STD_COLUMNS)) == len(STD_COLUMNS)


# ---------------------------------------------------------------------------
# normalize() basics
# ---------------------------------------------------------------------------


CHICAGO_FIELD_MAP = {
    "std_source_record_id": "id",
    "std_incident_id": "id",
    "std_incident_number": "case_number",
    "std_incident_date": "date",
    "std_reported_date": "date",
    "std_offense_code": "iucr",
    "std_offense_description": "description",
    "std_offense_category": "primary_type",
    "std_disposition": None,
    "std_address": "block",
    "std_zip_code": None,
    "std_neighborhood": "community_area",
    "std_district": "district",
    "std_beat": "beat",
    "std_division": None,
    "std_latitude": "latitude",
    "std_longitude": "longitude",
}

CHICAGO_PROVENANCE = {
    "std_city": "chicago",
    "std_city_display": "Chicago",
    "std_source_id": "chicago_crimes",
    "std_source_name": "Crimes - 2001 to Present",
    "std_source_dataset": "ijzp-q8t2",
    "std_source_url": "https://data.cityofchicago.org/resource/ijzp-q8t2.json",
}


def _row(**overrides):
    base = {
        "id": "12345",
        "case_number": "JG123456",
        "date": "2026-04-15T13:30:00.000",
        "iucr": "0820",
        "description": "$500 AND UNDER",
        "primary_type": "THEFT",
        "block": "001XX N STATE ST",
        "community_area": "32",
        "district": "001",
        "beat": "0111",
        "latitude": "41.880",
        "longitude": "-87.628",
    }
    base.update(overrides)
    return base


def test_normalize_produces_full_schema():
    df = normalize([_row()], CHICAGO_FIELD_MAP, "America/Chicago", provenance=CHICAGO_PROVENANCE)
    assert list(df.columns) == STD_COLUMNS
    assert len(df) == 1


def test_normalize_populates_provenance():
    df = normalize([_row()], CHICAGO_FIELD_MAP, "America/Chicago", provenance=CHICAGO_PROVENANCE)
    r = df.iloc[0]
    assert r["std_city"] == "chicago"
    assert r["std_source_dataset"] == "ijzp-q8t2"


def test_normalize_simple_field_mapping():
    df = normalize([_row()], CHICAGO_FIELD_MAP, "America/Chicago", provenance=CHICAGO_PROVENANCE)
    r = df.iloc[0]
    assert r["std_incident_id"] == "12345"
    assert r["std_incident_number"] == "JG123456"
    assert r["std_address"] == "001XX N STATE ST"
    assert r["std_offense_category"] == "THEFT"


def test_normalize_unmapped_columns_are_null():
    df = normalize([_row()], CHICAGO_FIELD_MAP, "America/Chicago", provenance=CHICAGO_PROVENANCE)
    r = df.iloc[0]
    assert pd.isna(r["std_disposition"])
    assert pd.isna(r["std_zip_code"])
    assert pd.isna(r["std_division"])


def test_normalize_latlon_coerced_to_float():
    df = normalize([_row()], CHICAGO_FIELD_MAP, "America/Chicago", provenance=CHICAGO_PROVENANCE)
    r = df.iloc[0]
    assert isinstance(r["std_latitude"], float)
    assert r["std_latitude"] == pytest.approx(41.880)
    assert r["std_longitude"] == pytest.approx(-87.628)


def test_normalize_latlon_blank_becomes_nan():
    df = normalize(
        [_row(latitude="", longitude=None)],
        CHICAGO_FIELD_MAP,
        "America/Chicago",
        provenance=CHICAGO_PROVENANCE,
    )
    r = df.iloc[0]
    assert pd.isna(r["std_latitude"])
    assert pd.isna(r["std_longitude"])


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------


def test_normalize_parses_naive_datetime_in_city_tz():
    """Socrata-style naive strings should be localized to the city's timezone."""
    df = normalize(
        [_row(date="2026-04-15T13:30:00.000")],
        CHICAGO_FIELD_MAP,
        "America/Chicago",
        provenance=CHICAGO_PROVENANCE,
    )
    ts = df.iloc[0]["std_incident_date"]
    assert ts is not None and not pd.isna(ts)
    assert str(ts.tz) == "America/Chicago"
    # 13:30 local time, not UTC.
    assert ts.hour == 13
    assert ts.minute == 30


def test_normalize_parses_epoch_ms_for_arcgis():
    """ArcGIS returns epoch milliseconds for date fields; we convert to city tz."""
    from datetime import datetime, timezone

    field_map = {"std_incident_date": "incident_occurred_at"}
    # Construct a known UTC instant and convert to epoch ms.
    utc_dt = datetime(2026, 4, 15, 17, 30, 0, tzinfo=timezone.utc)
    epoch_ms = int(utc_dt.timestamp() * 1000)
    df = normalize(
        [{"incident_occurred_at": epoch_ms}],
        field_map,
        "America/New_York",
    )
    ts = df.iloc[0]["std_incident_date"]
    assert ts is not None and not pd.isna(ts)
    assert str(ts.tz) == "America/New_York"
    # 17:30 UTC on 2026-04-15 is 13:30 EDT.
    assert ts.hour == 13
    assert ts.minute == 30
    assert ts.date().isoformat() == "2026-04-15"


def test_normalize_handles_empty_date_string():
    df = normalize(
        [_row(date="")],
        CHICAGO_FIELD_MAP,
        "America/Chicago",
        provenance=CHICAGO_PROVENANCE,
    )
    assert pd.isna(df.iloc[0]["std_incident_date"])


# ---------------------------------------------------------------------------
# Coalesce-fallback (the Detroit/Pittsburgh case)
# ---------------------------------------------------------------------------


DETROIT_FIELD_MAP = {
    "std_source_record_id": ["incident_entry_id", "crime_id", "ESRI_OID"],
    "std_incident_id": ["case_id", "report_number"],
    "std_reported_date": ["updated_in_ibr_at", "updated_at", "case_status_updated_at"],
    "std_incident_date": "incident_occurred_at",
}


def test_coalesce_picks_first_present():
    row = {
        "incident_entry_id": "A1",
        "crime_id": "B2",
        "ESRI_OID": 9999,
        "case_id": "CASE-1",
    }
    df = normalize([row], DETROIT_FIELD_MAP, "America/New_York")
    r = df.iloc[0]
    assert r["std_source_record_id"] == "A1"
    assert r["std_incident_id"] == "CASE-1"


def test_coalesce_skips_missing_keys():
    row = {"crime_id": "B2", "ESRI_OID": 9999, "report_number": "RN-7"}
    df = normalize([row], DETROIT_FIELD_MAP, "America/New_York")
    r = df.iloc[0]
    assert r["std_source_record_id"] == "B2"
    assert r["std_incident_id"] == "RN-7"


def test_coalesce_skips_null_and_empty_string():
    row = {
        "incident_entry_id": None,
        "crime_id": "",
        "ESRI_OID": 9999,
        "case_id": None,
        "report_number": "RN-7",
    }
    df = normalize([row], DETROIT_FIELD_MAP, "America/New_York")
    r = df.iloc[0]
    assert r["std_source_record_id"] == 9999
    assert r["std_incident_id"] == "RN-7"


def test_coalesce_all_null_returns_null():
    row = {"incident_entry_id": None, "crime_id": "", "case_id": None}
    df = normalize([row], DETROIT_FIELD_MAP, "America/New_York")
    r = df.iloc[0]
    assert pd.isna(r["std_source_record_id"])
    assert pd.isna(r["std_incident_id"])


# ---------------------------------------------------------------------------
# empty_frame()
# ---------------------------------------------------------------------------


def test_empty_frame_has_full_schema():
    df = empty_frame()
    assert list(df.columns) == STD_COLUMNS
    assert len(df) == 0
