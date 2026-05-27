"""Standardized incident schema and normalization.

The std_* schema is ported verbatim from tidycops `R/standardized_incidents.R`
(MIT, Anthony Galvan). normalize() applies a city's field_map to raw rows and
produces a DataFrame with every std_* column populated (or NaN/None when the
source doesn't expose that field).

Coalesce-fallback rule (matches R behavior):
    field_map values may be:
      - a string (single source field name)
      - a list of strings (try each in order; first non-null wins)
      - None (column always null for this city)
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo

import pandas as pd

# ---------------------------------------------------------------------------
# Standard columns (23 std_* fields)
# ---------------------------------------------------------------------------

STD_COLUMNS: list[str] = [
    "std_city",
    "std_city_display",
    "std_source_id",
    "std_source_name",
    "std_source_dataset",
    "std_source_url",
    "std_source_record_id",
    "std_incident_id",
    "std_incident_number",
    "std_incident_date",
    "std_reported_date",
    "std_offense_code",
    "std_offense_description",
    "std_offense_category",
    "std_disposition",
    "std_address",
    "std_zip_code",
    "std_neighborhood",
    "std_district",
    "std_beat",
    "std_division",
    "std_latitude",
    "std_longitude",
]

# Source-identity columns are populated from the SourceSpec/CitySpec, not field_map.
_PROVENANCE_COLUMNS = {
    "std_city",
    "std_city_display",
    "std_source_id",
    "std_source_name",
    "std_source_dataset",
    "std_source_url",
}

# Date columns get timezone-aware parsing.
_DATE_COLUMNS = {"std_incident_date", "std_reported_date"}

# Numeric columns get float coercion (geocoding).
_FLOAT_COLUMNS = {"std_latitude", "std_longitude"}


# SpotCrime extension (optional 9-category taxonomy applied downstream).
SPOTCRIME_COLUMNS: list[str] = [
    "std_spotcrime_category",
]


# ---------------------------------------------------------------------------
# Field-map application
# ---------------------------------------------------------------------------


def _coalesce(row: Mapping[str, Any], candidates: str | list[str] | tuple[str, ...] | None) -> Any:
    """Apply the coalesce-fallback rule for one std_* column.

    Returns the first value from `candidates` whose lookup yields a non-null,
    non-empty result. Matches the R behavior of coalescing across fallback
    fields (used heavily by Detroit, Pittsburgh, Cincinnati).
    """
    if candidates is None:
        return None
    if isinstance(candidates, str):
        candidates = (candidates,)
    for name in candidates:
        if name in row:
            v = row[name]
            if v is None:
                continue
            # Treat empty strings as missing; preserve 0 and False.
            if isinstance(v, str) and v.strip() == "":
                continue
            return v
    return None


def _parse_dt(value: Any, tz: ZoneInfo) -> pd.Timestamp | None:
    """Parse a raw timestamp into a timezone-aware pandas Timestamp.

    Strategy:
      - None / NaN / "" → None
      - Strings with explicit offset (Z or ±HH:MM) → convert to city tz
      - Naive strings → assume already in the city's local timezone, then
        attach that timezone (matches R's lubridate default)
      - epoch milliseconds (int/float) → UTC, then convert to city tz
    """
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        ts = pd.to_datetime(s, errors="coerce", utc=False)
        if ts is pd.NaT or pd.isna(ts):
            return None
        if ts.tzinfo is None:
            ts = ts.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
        else:
            ts = ts.tz_convert(tz)
        return ts
    if isinstance(value, (int, float)):
        # ArcGIS returns epoch milliseconds for date fields.
        # Heuristic: anything > 10^11 is ms; smaller is seconds.
        v = float(value)
        unit = "ms" if abs(v) > 1e11 else "s"
        ts = pd.to_datetime(v, unit=unit, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.tz_convert(tz)
    if isinstance(value, datetime):
        ts = pd.Timestamp(value)
        if ts.tzinfo is None:
            ts = ts.tz_localize(tz, nonexistent="shift_forward", ambiguous="NaT")
        else:
            ts = ts.tz_convert(tz)
        return ts
    return None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        f = float(value)
        return None if pd.isna(f) else f
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def normalize(
    rows: Iterable[Mapping[str, Any]],
    field_map: Mapping[str, str | list[str] | None],
    tz: str,
    *,
    provenance: Mapping[str, Any] | None = None,
) -> pd.DataFrame:
    """Map raw source rows into a DataFrame with all 23 std_* columns.

    Args:
        rows: Iterable of raw records (dict-like) from a platform fetcher.
        field_map: city source field_map (std_col → source field(s) or None).
        tz: IANA timezone string for date parsing (city local time).
        provenance: optional dict providing std_city / std_city_display /
            std_source_id / std_source_name / std_source_dataset / std_source_url.
            Any keys not in _PROVENANCE_COLUMNS are ignored.

    Returns:
        pandas.DataFrame with columns in STD_COLUMNS order.
    """
    tzinfo = ZoneInfo(tz)
    prov = {k: v for k, v in (provenance or {}).items() if k in _PROVENANCE_COLUMNS}

    out_rows: list[dict[str, Any]] = []
    for row in rows:
        rec: dict[str, Any] = {col: None for col in STD_COLUMNS}
        # Provenance first (constant across rows).
        for k, v in prov.items():
            rec[k] = v
        # Then field-map-driven columns.
        for std_col, candidates in field_map.items():
            if std_col in _PROVENANCE_COLUMNS:
                # field_map shouldn't override provenance; skip if it does.
                continue
            if std_col not in STD_COLUMNS:
                # Unknown std column — ignore quietly (forward-compatibility).
                continue
            value = _coalesce(row, candidates)
            if value is None:
                continue
            if std_col in _DATE_COLUMNS:
                rec[std_col] = _parse_dt(value, tzinfo)
            elif std_col in _FLOAT_COLUMNS:
                rec[std_col] = _to_float(value)
            else:
                rec[std_col] = value
        out_rows.append(rec)

    df = pd.DataFrame(out_rows, columns=STD_COLUMNS)

    # Enforce dtype on date columns so empty DataFrames still type correctly.
    for col in _DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True).dt.tz_convert(tzinfo)
    for col in _FLOAT_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def empty_frame() -> pd.DataFrame:
    """Return an empty DataFrame with the full std_* schema and correct dtypes."""
    return normalize([], field_map={}, tz="UTC", provenance=None)
