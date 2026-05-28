"""Tests for tidycop.dedup."""

from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tidycop import get_incidents
from tidycop.dedup import (
    DedupStore,
    content_hash,
    filter_new,
    open_store,
)
from tidycop.schema import STD_COLUMNS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _row(**overrides) -> dict:
    rec = {col: None for col in STD_COLUMNS}
    rec["std_city"] = "chicago"
    rec["std_city_display"] = "Chicago"
    rec["std_source_id"] = "chicago_crimes"
    rec["std_source_name"] = "Crimes - 2001 to Present"
    rec["std_source_dataset"] = "ijzp-q8t2"
    rec["std_source_url"] = "https://example.com"
    rec["std_incident_id"] = "abc123"
    rec["std_incident_number"] = "JZ123456"
    rec["std_offense_description"] = "THEFT"
    rec["std_incident_date"] = pd.Timestamp("2026-04-01 12:00", tz="America/Chicago")
    rec.update(overrides)
    return rec


# ---------------------------------------------------------------------------
# content_hash
# ---------------------------------------------------------------------------


def test_content_hash_is_stable_across_calls():
    r = _row()
    assert content_hash(r) == content_hash(r)


def test_content_hash_ignores_provenance_changes():
    """A row that moves between sources (e.g. cincinnati legacy → current)
    but keeps the same identity + facts should hash to the same value."""
    a = _row(std_source_id="legacy", std_source_name="Old", std_source_dataset="aaa-1111")
    b = _row(std_source_id="current", std_source_name="New", std_source_dataset="bbb-2222")
    assert content_hash(a) == content_hash(b)


def test_content_hash_changes_when_facts_change():
    a = _row(std_incident_id="abc")
    b = _row(std_incident_id="xyz")
    assert content_hash(a) != content_hash(b)


def test_content_hash_handles_naat():
    """NaT/NaN in date or numeric fields shouldn't crash."""
    r = _row()
    r["std_incident_date"] = pd.NaT
    r["std_latitude"] = float("nan")
    # Two NaT rows should match each other.
    assert content_hash(r) == content_hash(
        _row(std_incident_date=pd.NaT, std_latitude=float("nan"))
    )


# ---------------------------------------------------------------------------
# DedupStore
# ---------------------------------------------------------------------------


def test_store_creates_schema(tmp_path: Path):
    db = tmp_path / "seen.sqlite"
    store = DedupStore(db)
    assert db.exists()
    # Verify table + index exist.
    conn = sqlite3.connect(str(db))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "seen_incidents" in tables
    indices = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert "idx_seen_city_source" in indices
    conn.close()
    store.close()


def test_store_record_then_has_seen(tmp_path: Path):
    with open_store(tmp_path / "seen.sqlite") as store:
        assert not store.has_seen("chicago", "chicago_crimes", "h1")
        assert store.record("chicago", "chicago_crimes", "h1") is True
        assert store.has_seen("chicago", "chicago_crimes", "h1")
        # second record is a no-op
        assert store.record("chicago", "chicago_crimes", "h1") is False


def test_store_isolates_by_city_and_source(tmp_path: Path):
    with open_store(tmp_path / "seen.sqlite") as store:
        store.record("chicago", "chicago_crimes", "h1")
        assert store.has_seen("chicago", "chicago_crimes", "h1")
        # Different city: not seen.
        assert not store.has_seen("seattle", "chicago_crimes", "h1")
        # Different source_id: not seen.
        assert not store.has_seen("chicago", "other_source", "h1")


def test_store_record_many_bulk_counts(tmp_path: Path):
    with open_store(tmp_path / "seen.sqlite") as store:
        inserted, skipped = store.record_many("chicago", "src", ["a", "b", "c"])
        assert (inserted, skipped) == (3, 0)
        # Re-record b: only "d" is new.
        inserted, skipped = store.record_many("chicago", "src", ["b", "d"])
        assert (inserted, skipped) == (1, 1)


def test_store_stats(tmp_path: Path):
    with open_store(tmp_path / "seen.sqlite") as store:
        store.record_many("chicago", "src", ["a", "b"])
        store.record("seattle", "src", "x")
        all_stats = store.stats()
        assert all_stats["total"] == 3
        chi_stats = store.stats("chicago")
        assert chi_stats["total"] == 2


def test_store_requires_path_for_writes():
    store = DedupStore(None)
    with pytest.raises(RuntimeError):
        store.record("chicago", "src", "h1")


# ---------------------------------------------------------------------------
# filter_new
# ---------------------------------------------------------------------------


def test_filter_new_first_call_returns_all(tmp_path: Path):
    df = pd.DataFrame([_row(std_incident_id=f"id{i}") for i in range(5)], columns=STD_COLUMNS)
    with open_store(tmp_path / "seen.sqlite") as store:
        out = filter_new(df, city="chicago", source_id="chicago_crimes", store=store)
    assert len(out) == 5


def test_filter_new_second_call_returns_nothing(tmp_path: Path):
    df = pd.DataFrame([_row(std_incident_id=f"id{i}") for i in range(3)], columns=STD_COLUMNS)
    with open_store(tmp_path / "seen.sqlite") as store:
        first = filter_new(df, city="chicago", source_id="chicago_crimes", store=store)
        second = filter_new(df, city="chicago", source_id="chicago_crimes", store=store)
    assert len(first) == 3
    assert len(second) == 0


def test_filter_new_returns_only_delta(tmp_path: Path):
    df1 = pd.DataFrame([_row(std_incident_id=f"id{i}") for i in range(3)], columns=STD_COLUMNS)
    df2 = pd.DataFrame(
        [_row(std_incident_id=f"id{i}") for i in range(1, 6)], columns=STD_COLUMNS
    )  # overlap id1, id2; new id3, id4, id5
    with open_store(tmp_path / "seen.sqlite") as store:
        filter_new(df1, city="chicago", source_id="chicago_crimes", store=store)
        out2 = filter_new(df2, city="chicago", source_id="chicago_crimes", store=store)
    assert len(out2) == 3
    assert set(out2["std_incident_id"]) == {"id3", "id4", "id5"}


def test_filter_new_handles_empty_df(tmp_path: Path):
    df = pd.DataFrame(columns=STD_COLUMNS)
    with open_store(tmp_path / "seen.sqlite") as store:
        out = filter_new(df, city="chicago", source_id="chicago_crimes", store=store)
    assert len(out) == 0


# ---------------------------------------------------------------------------
# get_incidents() integration
# ---------------------------------------------------------------------------


class _StubFetcher:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self, source, start_date, end_date, *, limit=1000):
        return list(self.rows)


def _chicago_raw(n: int):
    """Raw rows shaped like Chicago's Socrata response, distinct ids."""
    return [
        {
            "id": f"id{i}",
            "case_number": f"JZ{i:05d}",
            "date": "2026-04-01T12:00:00.000",
            "iucr": "0820",
            "description": "THEFT $500 AND UNDER",
            "primary_type": "THEFT",
            "block": "001XX N STATE ST",
            "community_area": "8",
            "district": "001",
            "beat": "0111",
            "latitude": "41.0",
            "longitude": "-87.0",
        }
        for i in range(n)
    ]


def test_get_incidents_dedup_filters_duplicates_across_calls(tmp_path: Path):
    db = tmp_path / "seen.sqlite"
    fetcher = _StubFetcher(_chicago_raw(4))

    first = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        fetcher=fetcher,
        dedup_db=db,
    )
    second = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        fetcher=fetcher,
        dedup_db=db,
    )
    assert len(first) == 4
    assert len(second) == 0


def test_get_incidents_dedup_keeps_new_rows_only(tmp_path: Path):
    db = tmp_path / "seen.sqlite"

    f1 = _StubFetcher(_chicago_raw(3))  # id0, id1, id2
    first = get_incidents("chicago", date(2026, 4, 1), date(2026, 4, 1), fetcher=f1, dedup_db=db)
    assert len(first) == 3

    # Second fetch: 3 of the same rows + 2 new ones.
    overlap = _chicago_raw(3)
    new_rows = [
        {**overlap[0], "id": "id10", "case_number": "JZ10"},
        {**overlap[0], "id": "id11", "case_number": "JZ11"},
    ]
    f2 = _StubFetcher(overlap + new_rows)
    second = get_incidents("chicago", date(2026, 4, 1), date(2026, 4, 1), fetcher=f2, dedup_db=db)
    assert len(second) == 2
    assert set(second["std_incident_id"]) == {"id10", "id11"}


def test_get_incidents_dedup_city_full_view_stays_aligned(tmp_path: Path):
    """When dedup drops half the rows, city_full's raw+std side must also drop."""
    db = tmp_path / "seen.sqlite"
    raw = _chicago_raw(4)
    fetcher = _StubFetcher(raw)

    first = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        view="city_full",
        fetcher=fetcher,
        dedup_db=db,
    )
    assert len(first) == 4

    # Re-fetch — all 4 should drop out, frame should be empty.
    fetcher2 = _StubFetcher(raw)
    second = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        view="city_full",
        fetcher=fetcher2,
        dedup_db=db,
    )
    assert len(second) == 0
    # Native + std columns still exist on the empty frame.
    assert "std_city" in second.columns


def test_get_incidents_no_dedup_db_returns_everything(tmp_path: Path):
    """Default (dedup_db=None) — caller pays no sqlite cost, no dedup."""
    fetcher = _StubFetcher(_chicago_raw(3))
    df = get_incidents("chicago", date(2026, 4, 1), date(2026, 4, 1), fetcher=fetcher)
    assert len(df) == 3
    # And again with same rows — no filtering.
    df2 = get_incidents(
        "chicago", date(2026, 4, 1), date(2026, 4, 1), fetcher=_StubFetcher(_chicago_raw(3))
    )
    assert len(df2) == 3
