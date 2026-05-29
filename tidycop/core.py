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
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from tidycop.platform import BaseFetcher, get_fetcher
from tidycop.registry import CitySpec, SourceSpec, get_city_spec, get_city_spec_from_path
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
    dedup_db: Path | str | None = None,
    classify_spotcrime: bool = False,
    registry_path: Path | str | None = None,
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
        dedup_db: Optional path to a sqlite DB used by ``tidycop.dedup`` to
            track ``(city, source_id, content_hash)`` triples. When supplied,
            only rows whose hash hasn't been recorded before are returned
            (and every hash from this call is recorded for next time).
            Only applies to the normalized ``comparable`` and ``city_full``
            views; ``city_raw`` bypasses dedup entirely.
        classify_spotcrime: when True, adds a ``std_spotcrime_category``
            column populated from the source's ``spotcrime_category_map``.
            Rows whose native category doesn't map remain null. Only
            applies to ``comparable`` and ``city_full`` views.
        registry_path: Optional path to a downstream registry YAML. When
            supplied, the city is resolved from that file instead of the
            bundled ``registry/cities.yaml`` (used by downstream consumers
            like SpotCrime data2 wrappers to keep product-specific city
            entries out of the upstream-parity library).

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

    if registry_path is not None:
        city_spec = get_city_spec_from_path(city, registry_path)
    else:
        city_spec = get_city_spec(city)  # raises KeyError on unknown city
    source = _select_source(city_spec, start, end)
    fetcher = fetcher or get_fetcher(source.provider)

    raw = list(fetcher.fetch(source, start, end, limit=limit))

    if view == "city_raw":
        return pd.DataFrame(raw)

    provenance = _build_provenance(city_spec, source)
    normalized = normalize(raw, source.field_map, city_spec.timezone, provenance=provenance)

    # Track which raw rows survive dedup so view='city_full' stays aligned.
    keep_mask: list[bool] | None = None
    if dedup_db is not None:
        # Lazy import so the optional sqlite layer doesn't load on every call.
        from tidycop.dedup import DedupStore, content_hash

        with DedupStore(dedup_db) as store:
            hashes = [content_hash(r) for r in normalized.to_dict(orient="records")]
            keep_mask = [not store.has_seen(city_spec.city, source.source_id, h) for h in hashes]
            store.record_many(city_spec.city, source.source_id, hashes)
        normalized = normalized.loc[keep_mask].reset_index(drop=True)

    if classify_spotcrime:
        # Lazy import: keep classifier optional.
        from tidycop.classifier import classify_frame

        normalized = classify_frame(normalized, source.spotcrime_category_map)

    if view == "comparable":
        return normalized

    if view == "city_full":
        # Native + std side-by-side. If a raw field name collides with a
        # std_* column, the std_* wins (rename the native one with a suffix).
        if not raw:
            return normalized
        raw_df = pd.DataFrame(raw)
        if keep_mask is not None:
            raw_df = raw_df.loc[keep_mask].reset_index(drop=True)
        clashes = [c for c in raw_df.columns if c in STD_COLUMNS]
        if clashes:
            raw_df = raw_df.rename(columns={c: f"{c}__raw" for c in clashes})
        return pd.concat([raw_df.reset_index(drop=True), normalized.reset_index(drop=True)], axis=1)

    raise ValueError(f"unknown view {view!r}; expected comparable | city_full | city_raw")
