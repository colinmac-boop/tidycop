"""Core incident fetching logic.

Wires the registry → platform fetcher → schema normalizer into the single
public ``get_incidents()`` entrypoint.

For MVP we assume one active source per city per date range. When a city's
sources are split across migrations (`active_from` / `active_to`), the first
source whose window overlaps [start_date, end_date] wins. None of the 5 MVP
cities currently exercise that split, but Cincinnati and Cleveland will.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

import pandas as pd

from tidycop.platform import BaseFetcher, get_fetcher
from tidycop.registry import CitySpec, SourceSpec, get_city_spec
from tidycop.schema import STD_COLUMNS, normalize

View = Literal["comparable", "city_full", "city_raw"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.split("T")[0]).date()
    raise TypeError(f"start_date/end_date must be date or ISO string, got {type(value).__name__}")


def _source_overlaps(source: SourceSpec, start: date, end: date) -> bool:
    """True if [active_from, active_to] overlaps [start, end] (None = open-ended)."""
    if source.active_from is not None and source.active_from > end:
        return False
    if source.active_to is not None and source.active_to < start:
        return False
    return True


def _select_source(city: CitySpec, start: date, end: date) -> SourceSpec:
    """Pick the first source whose active window overlaps the requested range."""
    for src in city.sources:
        if _source_overlaps(src, start, end):
            return src
    raise ValueError(
        f"no source for {city.city!r} covers {start.isoformat()}..{end.isoformat()} "
        f"(available: {[(s.source_id, s.active_from, s.active_to) for s in city.sources]})"
    )


def _build_provenance(city: CitySpec, source: SourceSpec) -> dict[str, Any]:
    return {
        "std_city": city.city,
        "std_city_display": city.display_name,
        "std_source_id": source.source_id,
        "std_source_name": source.display_name,
        "std_source_dataset": source.dataset_id,
        "std_source_url": source.base_url,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_incidents(
    city: str,
    start_date: date | str,
    end_date: date | str,
    *,
    view: View = "comparable",
    limit: int = 1000,
    fetcher: BaseFetcher | None = None,
) -> pd.DataFrame:
    """Fetch incidents for a supported city.

    Args:
        city: City key or alias (e.g. ``"chicago"``, ``"sf"``, ``"pgh"``).
        start_date: Start date (inclusive). ``date`` or ISO string.
        end_date: End date (inclusive). ``date`` or ISO string.
        view: Output mode.
            - ``"comparable"``: only the 23 ``std_*`` columns (cross-city analysis).
            - ``"city_full"``: raw native fields + ``std_*`` columns side-by-side.
            - ``"city_raw"``: untouched raw source payload (no ``std_*`` columns).
        limit: Maximum records to return overall (not per page).
        fetcher: Optional pre-built fetcher instance (used by tests + advanced
            callers who want custom session/auth/retry). When ``None`` we
            dispatch on the source's provider.

    Returns:
        ``pandas.DataFrame``. Column shape depends on ``view``.

    Raises:
        KeyError: if ``city`` is not in the registry.
        ValueError: if the date range is invalid or no source covers it.
        NotImplementedError: if the city's provider isn't wired yet
            (ArcGIS for Detroit, CKAN for Pittsburgh — Day 6 and 7).
    """
    start = _coerce_date(start_date)
    end = _coerce_date(end_date)
    if end < start:
        raise ValueError(f"end_date ({end}) is before start_date ({start})")

    city_spec = get_city_spec(city)  # raises KeyError on unknown city
    source = _select_source(city_spec, start, end)
    fetcher = fetcher or get_fetcher(source.provider)

    raw = list(fetcher.fetch(source, start, end, limit=limit))

    if view == "city_raw":
        return pd.DataFrame(raw)

    provenance = _build_provenance(city_spec, source)
    normalized = normalize(raw, source.field_map, city_spec.timezone, provenance=provenance)

    if view == "comparable":
        return normalized

    if view == "city_full":
        # Native + std side-by-side. If a raw field name collides with a
        # std_* column, the std_* wins (rename the native one with a suffix).
        if not raw:
            return normalized
        raw_df = pd.DataFrame(raw)
        clashes = [c for c in raw_df.columns if c in STD_COLUMNS]
        if clashes:
            raw_df = raw_df.rename(columns={c: f"{c}__raw" for c in clashes})
        return pd.concat([raw_df.reset_index(drop=True), normalized.reset_index(drop=True)], axis=1)

    raise ValueError(f"unknown view {view!r}; expected comparable | city_full | city_raw")
