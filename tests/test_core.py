"""Tests for tidycop.core.get_incidents.

A FakeFetcher avoids any network use; live end-to-end coverage lives in
tests/test_socrata_live.py.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

import tidycop
from tidycop.core import _select_source, get_incidents
from tidycop.platform.base import BaseFetcher
from tidycop.registry import CitySpec, SourceSpec, get_city_spec
from tidycop.schema import STD_COLUMNS

# ---------------------------------------------------------------------------
# Fake fetcher
# ---------------------------------------------------------------------------


class FakeFetcher(BaseFetcher):
    """Returns canned rows; records the SourceSpec it was called with."""

    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.calls: list[tuple[SourceSpec, date, date, int]] = []

    def fetch(self, source, start_date, end_date, *, limit=1000):
        self.calls.append((source, start_date, end_date, limit))
        return list(self.rows[:limit])


CHICAGO_ROWS = [
    {
        "id": "111",
        "case_number": "JG111",
        "date": "2026-04-15T13:30:00.000",
        "iucr": "0820",
        "description": "$500 AND UNDER",
        "primary_type": "THEFT",
        "block": "001XX N STATE ST",
        "community_area": "32",
        "district": "001",
        "beat": "0111",
        "latitude": "41.88",
        "longitude": "-87.63",
    },
    {
        "id": "222",
        "case_number": "JG222",
        "date": "2026-04-16T09:00:00.000",
        "iucr": "031A",
        "description": "ARMED - HANDGUN",
        "primary_type": "ROBBERY",
        "block": "010XX W FULLERTON AVE",
        "community_area": "7",
        "district": "018",
        "beat": "1813",
        "latitude": "41.925",
        "longitude": "-87.655",
    },
]


# ---------------------------------------------------------------------------
# Smoke
# ---------------------------------------------------------------------------


def test_get_incidents_default_view_returns_std_only():
    fake = FakeFetcher(CHICAGO_ROWS)
    df = get_incidents("chicago", "2026-04-15", "2026-04-16", fetcher=fake)
    assert list(df.columns) == STD_COLUMNS
    assert len(df) == 2


def test_get_incidents_populates_provenance():
    fake = FakeFetcher(CHICAGO_ROWS)
    df = get_incidents("chicago", "2026-04-15", "2026-04-16", fetcher=fake)
    r = df.iloc[0]
    assert r["std_city"] == "chicago"
    assert r["std_city_display"] == "Chicago"
    assert r["std_source_id"] == "chicago_crimes"
    assert r["std_source_dataset"] == "ijzp-q8t2"


def test_get_incidents_normalizes_fields():
    fake = FakeFetcher(CHICAGO_ROWS)
    df = get_incidents("chicago", "2026-04-15", "2026-04-16", fetcher=fake)
    r0, r1 = df.iloc[0], df.iloc[1]
    assert r0["std_incident_id"] == "111"
    assert r0["std_offense_category"] == "THEFT"
    assert r1["std_offense_category"] == "ROBBERY"
    assert r0["std_latitude"] == pytest.approx(41.88)
    # Date came through as a timezone-aware Timestamp in city tz.
    assert str(r0["std_incident_date"].tz) == "America/Chicago"


def test_get_incidents_passes_dates_and_limit_to_fetcher():
    fake = FakeFetcher(CHICAGO_ROWS)
    get_incidents("chicago", "2026-04-15", "2026-04-16", limit=50, fetcher=fake)
    src, start, end, limit = fake.calls[0]
    assert src.source_id == "chicago_crimes"
    assert start == date(2026, 4, 15)
    assert end == date(2026, 4, 16)
    assert limit == 50


def test_get_incidents_resolves_alias():
    fake = FakeFetcher([])
    get_incidents("SF", "2026-04-01", "2026-04-02", fetcher=fake)
    assert fake.calls[0][0].source_id == "san_francisco_incidents"


def test_get_incidents_accepts_date_objects():
    fake = FakeFetcher(CHICAGO_ROWS)
    df = get_incidents("chicago", date(2026, 4, 15), date(2026, 4, 16), fetcher=fake)
    assert len(df) == 2


# ---------------------------------------------------------------------------
# View modes
# ---------------------------------------------------------------------------


def test_view_city_raw_returns_untouched_payload():
    fake = FakeFetcher(CHICAGO_ROWS)
    df = get_incidents("chicago", "2026-04-15", "2026-04-16", view="city_raw", fetcher=fake)
    # No std_* columns; native field names preserved.
    assert "id" in df.columns
    assert "primary_type" in df.columns
    assert not any(c.startswith("std_") for c in df.columns)
    assert len(df) == 2


def test_view_city_full_has_native_plus_std():
    fake = FakeFetcher(CHICAGO_ROWS)
    df = get_incidents("chicago", "2026-04-15", "2026-04-16", view="city_full", fetcher=fake)
    # Native fields present.
    for native in ("id", "primary_type", "case_number"):
        assert native in df.columns, f"missing native field {native!r}"
    # All std_* columns present.
    for std in STD_COLUMNS:
        assert std in df.columns
    assert len(df) == 2


def test_view_city_full_empty_returns_std_only():
    fake = FakeFetcher([])
    df = get_incidents("chicago", "2026-04-15", "2026-04-16", view="city_full", fetcher=fake)
    assert list(df.columns) == STD_COLUMNS
    assert len(df) == 0


def test_view_unknown_raises():
    fake = FakeFetcher(CHICAGO_ROWS)
    with pytest.raises(ValueError, match="unknown view"):
        get_incidents("chicago", "2026-04-15", "2026-04-16", view="bogus", fetcher=fake)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_unknown_city_raises_key_error():
    with pytest.raises(KeyError):
        get_incidents("atlantis", "2026-04-15", "2026-04-16")


def test_inverted_date_range_raises():
    fake = FakeFetcher([])
    with pytest.raises(ValueError, match="before start_date"):
        get_incidents("chicago", "2026-04-30", "2026-04-01", fetcher=fake)


def test_unwired_provider_raises_not_implemented(monkeypatch):
    """Provider → fetcher dispatch must raise NotImplementedError for unknown providers.

    All 5 MVP cities now have working providers (socrata/arcgis/ckan).
    Patch the registry to verify the not-implemented path still fires.
    """
    from tidycop import platform

    monkeypatch.setitem(platform._REGISTRY, "madeup", platform._REGISTRY["socrata"])  # noqa: SLF001
    monkeypatch.delitem(platform._REGISTRY, "madeup")

    fake_city = type(get_city_spec("chicago"))(
        city="x",
        display_name="X",
        timezone="UTC",
        sources=(
            SourceSpec(
                source_id="x",
                display_name="x",
                provider="madeup",
                dataset_id="d",
                base_url="https://example/",
                date_field="d",
                field_map={},
            ),
        ),
    )
    # Patch get_city_spec to return our fake.
    import tidycop.core as core_mod

    monkeypatch.setattr(core_mod, "get_city_spec", lambda c: fake_city)
    with pytest.raises(NotImplementedError, match="no fetcher registered for provider"):
        get_incidents("anything", "2026-04-15", "2026-04-16")


# ---------------------------------------------------------------------------
# Source selection (active_from / active_to)
# ---------------------------------------------------------------------------


def _src(source_id, active_from=None, active_to=None):
    return SourceSpec(
        source_id=source_id,
        display_name=source_id,
        provider="socrata",
        dataset_id="ds",
        base_url="https://example/",
        date_field="date",
        field_map={},
        active_from=active_from,
        active_to=active_to,
    )


def test_select_source_picks_open_ended_when_no_dates():
    city = CitySpec(city="x", display_name="X", timezone="UTC", sources=(_src("only"),))
    assert _select_source(city, date(2026, 1, 1), date(2026, 12, 31)).source_id == "only"


def test_select_source_picks_legacy_for_old_range():
    city = CitySpec(
        city="x",
        display_name="X",
        timezone="UTC",
        sources=(
            _src("legacy", active_to=date(2024, 6, 2)),
            _src("current", active_from=date(2024, 6, 3)),
        ),
    )
    assert _select_source(city, date(2023, 1, 1), date(2023, 6, 30)).source_id == "legacy"


def test_select_source_picks_current_for_recent_range():
    city = CitySpec(
        city="x",
        display_name="X",
        timezone="UTC",
        sources=(
            _src("legacy", active_to=date(2024, 6, 2)),
            _src("current", active_from=date(2024, 6, 3)),
        ),
    )
    assert _select_source(city, date(2025, 1, 1), date(2025, 12, 31)).source_id == "current"


def test_select_source_returns_first_overlap_when_range_spans_cutover():
    """Per-row source dispatch is a future feature; for now we just pick the first that overlaps."""
    city = CitySpec(
        city="x",
        display_name="X",
        timezone="UTC",
        sources=(
            _src("legacy", active_to=date(2024, 6, 2)),
            _src("current", active_from=date(2024, 6, 3)),
        ),
    )
    # 2024-05 spans into legacy; legacy comes first in tuple, so we get it.
    assert _select_source(city, date(2024, 5, 1), date(2024, 7, 31)).source_id == "legacy"


def test_select_source_raises_when_nothing_overlaps():
    city = CitySpec(
        city="x",
        display_name="X",
        timezone="UTC",
        sources=(_src("only", active_from=date(2024, 1, 1), active_to=date(2024, 12, 31)),),
    )
    with pytest.raises(ValueError, match="no source"):
        _select_source(city, date(2026, 1, 1), date(2026, 12, 31))


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_top_level_import_exposes_get_incidents():
    assert tidycop.get_incidents is get_incidents
