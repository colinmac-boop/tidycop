"""Persistent deduplication layer for incident fetches.

The producer for SpotCrime / spotcops needs to know which records it has
already shipped downstream, so it can ship only the *new* records on each
incremental pull. tidycop itself is mostly stateless — given a city and a
date window, it returns whatever the upstream feed currently exposes,
which is sometimes the same row N times across N fetches (rolling
windows, late edits, re-publishes).

This module provides a small sqlite-backed "seen set" keyed by:

    (std_city, std_source_id, content_hash)

content_hash is a stable SHA-256 over a canonical JSON encoding of the
row's std_* fields (provenance + identity columns excluded — those change
when a city splits its sources, but the underlying incident did not).

Usage::

    from pathlib import Path
    from tidycop import get_incidents

    df = get_incidents(
        "chicago",
        "2026-04-01",
        "2026-04-07",
        dedup_db=Path("./state/seen.sqlite"),
    )
    # df now only contains rows we hadn't recorded in seen.sqlite before;
    # the new rows are already recorded for the next call.

Opt-in: passing ``dedup_db=None`` (the default) skips everything here.

Design notes:
    * sqlite, not Postgres: zero ops, fine for single-tenant producers.
    * WAL + single writer per process: safe enough for our access pattern.
    * Content hash uses ``sort_keys=True`` + ``default=str`` so we get a
      stable encoding for pandas Timestamps and floats.
    * Schema is intentionally tiny — one table, one composite primary key,
      one created_at column for forensics. No migrations yet; if the
      shape needs to change in v0.3 we'll bump a SCHEMA_VERSION pragma.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

import pandas as pd

from tidycop.schema import STD_COLUMNS

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_VERSION = 1

# Columns whose values change purely because of how a city splits its sources
# (e.g. Cincinnati legacy → current), without the underlying incident
# changing. Excluded from content hash.
_HASH_EXCLUDE: set[str] = {
    "std_city",
    "std_city_display",
    "std_source_id",
    "std_source_name",
    "std_source_dataset",
    "std_source_url",
}

# Columns we *do* include in the hash. Cached for speed.
_HASH_COLUMNS: list[str] = [c for c in STD_COLUMNS if c not in _HASH_EXCLUDE]


_DDL = """
CREATE TABLE IF NOT EXISTS seen_incidents (
    city          TEXT NOT NULL,
    source_id     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    PRIMARY KEY (city, source_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_seen_city_source
    ON seen_incidents (city, source_id);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canonical(value: Any) -> Any:
    """Convert non-JSON-native values to stable string forms."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        # UTC ISO is canonical; preserves the original instant regardless of
        # whether the row arrived from Socrata-with-tz or ArcGIS-epoch-ms.
        return value.tz_convert("UTC").isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


def content_hash(row: dict[str, Any] | pd.Series) -> str:
    """Stable SHA-256 over the dedupable subset of a normalized row.

    Public so callers can compute their own hashes outside the writer
    (useful for downstream auditing / replay).
    """
    if isinstance(row, pd.Series):
        items = {col: _canonical(row.get(col)) for col in _HASH_COLUMNS}
    else:
        items = {col: _canonical(row.get(col)) for col in _HASH_COLUMNS}
    blob = json.dumps(items, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class DedupStore:
    """sqlite-backed seen-set for ``(city, source_id, content_hash)`` triples.

    Thread safety: ``check_same_thread=False`` so a single store can be
    handed to multiple workers, but the caller is responsible for
    serializing writes (we use a single ``Connection`` + WAL).
    """

    def __init__(self, db_path: Path | str | None) -> None:
        self.db_path = Path(db_path) if db_path else None
        self._conn: sqlite3.Connection | None = None
        if self.db_path is not None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(
                str(self.db_path), check_same_thread=False, isolation_level=None
            )
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_DDL)

    # --------------------------------------------------------------- context

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "DedupStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ----------------------------------------------------------------- core

    def _ensure(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("DedupStore was constructed with db_path=None; cannot write")
        return self._conn

    def has_seen(self, city: str, source_id: str, hash_: str) -> bool:
        conn = self._ensure()
        cur = conn.execute(
            "SELECT 1 FROM seen_incidents WHERE city=? AND source_id=? AND content_hash=? LIMIT 1",
            (city, source_id, hash_),
        )
        return cur.fetchone() is not None

    def record(self, city: str, source_id: str, hash_: str) -> bool:
        """Record one hash. Returns True if it was newly inserted, False if already known."""
        conn = self._ensure()
        now = datetime.now(timezone.utc).isoformat()
        try:
            conn.execute(
                "INSERT INTO seen_incidents (city, source_id, content_hash, first_seen_at) "
                "VALUES (?, ?, ?, ?)",
                (city, source_id, hash_, now),
            )
            return True
        except sqlite3.IntegrityError:
            return False

    def record_many(self, city: str, source_id: str, hashes: Iterable[str]) -> tuple[int, int]:
        """Bulk-record hashes. Returns ``(inserted, skipped)``.

        Uses ``INSERT OR IGNORE`` for speed; counts are taken from
        ``rowcount`` deltas per row to keep accurate stats.
        """
        conn = self._ensure()
        now = datetime.now(timezone.utc).isoformat()
        inserted = 0
        skipped = 0
        with conn:  # one txn for the batch
            for h in hashes:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO seen_incidents "
                    "(city, source_id, content_hash, first_seen_at) VALUES (?, ?, ?, ?)",
                    (city, source_id, h, now),
                )
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
        return inserted, skipped

    def stats(self, city: str | None = None) -> dict[str, Any]:
        """Quick summary for observability."""
        conn = self._ensure()
        if city is None:
            cur = conn.execute(
                "SELECT COUNT(*), MIN(first_seen_at), MAX(first_seen_at) FROM seen_incidents"
            )
        else:
            cur = conn.execute(
                "SELECT COUNT(*), MIN(first_seen_at), MAX(first_seen_at) FROM seen_incidents WHERE city=?",
                (city,),
            )
        total, first, last = cur.fetchone()
        return {"city": city, "total": total, "first_seen_at": first, "last_seen_at": last}


# ---------------------------------------------------------------------------
# DataFrame filter
# ---------------------------------------------------------------------------


def filter_new(
    df: pd.DataFrame,
    *,
    city: str,
    source_id: str,
    store: DedupStore,
) -> pd.DataFrame:
    """Return only rows from ``df`` whose content_hash is new in ``store``.

    Side effect: records every hash from the input frame (both kept and
    skipped) so the next call will see them as already-seen.

    A side-effecting "filter that also writes" feels mildly evil but it
    matches how the spotcops producer actually uses this: pull, write
    downstream, mark as seen — in one atomic-ish step. We swallow the
    skipped rows here so callers don't have to.
    """
    if df.empty:
        return df

    # Compute hashes column-wise for speed.
    hashes: list[str] = [content_hash(row) for row in df.to_dict(orient="records")]
    mask = [not store.has_seen(city, source_id, h) for h in hashes]

    # Record everything seen this call (idempotent: dupes get INSERT OR IGNORE).
    store.record_many(city, source_id, hashes)

    out = df.loc[mask].reset_index(drop=True)
    logger.debug(
        "dedup %s/%s: %d in -> %d new (%d already seen)",
        city,
        source_id,
        len(df),
        len(out),
        len(df) - len(out),
    )
    return out


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


@contextmanager
def open_store(db_path: Path | str) -> Iterator[DedupStore]:
    """Context-managed DedupStore. Ensures the connection is closed."""
    store = DedupStore(db_path)
    try:
        yield store
    finally:
        store.close()
