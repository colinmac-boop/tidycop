"""Per-city live smoke tests for every registered city.

Opt-in: set ``TIDYCOP_LIVE_ALL=1`` to enable. Skipped by default so the
default ``pytest`` run stays offline. Individual provider env vars
(``TIDYCOP_LIVE_SOCRATA`` / ``TIDYCOP_LIVE_ARCGIS`` / ``TIDYCOP_LIVE_CKAN``)
still run the older, hand-curated smoke tests in this directory; this file
is the wide net that exercises every city in the registry against the live
endpoint behind its first active-today source.

Each city test:
  1. Selects the first source whose [active_from, active_to] window covers
     the chosen smoke window (default: last 90-ish days).
  2. Calls ``get_incidents(city, ...)`` with a tight row cap.
  3. Asserts we got a DataFrame back (may be empty for rolling/historical
     feeds that don't cover that exact window).

We deliberately don't assert ``len > 0`` for every city — some feeds
(Providence's 180-day rolling log, Fort Lauderdale's historical cap,
Naperville's two slices) won't have data in any given recent window.
Instead we assert that the call *returns* without exception and that
shape + dtypes are sane.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

import pandas as pd
import pytest

from tidycop import get_incidents
from tidycop.registry import _reset_cache, load_registry
from tidycop.schema import STD_COLUMNS

LIVE = os.environ.get("TIDYCOP_LIVE_ALL") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE, reason="set TIDYCOP_LIVE_ALL=1 to run wide live network smoke tests"
)


def _all_city_keys() -> list[str]:
    _reset_cache()
    return sorted(load_registry().keys())


def _pick_window(spec) -> tuple[date, date]:
    """Choose a 7-day window inside whatever source is plausibly active."""
    today = date.today()
    # Default: 14..7 days ago — gives publishers time to ingest.
    end = today - timedelta(days=7)
    start = end - timedelta(days=7)

    # If every source has an active_to in the past, use the last 7 days
    # of the most recent source's window instead.
    latest_active_to = None
    for src in spec.sources:
        if src.active_to is not None:
            if latest_active_to is None or src.active_to > latest_active_to:
                latest_active_to = src.active_to
        else:
            # at least one source is open-ended — recent window is fine.
            return start, end
    if latest_active_to is not None:
        end = latest_active_to
        start = end - timedelta(days=7)
    return start, end


@pytest.mark.parametrize("city_key", _all_city_keys())
def test_live_city_smoke(city_key: str) -> None:
    _reset_cache()
    spec = load_registry()[city_key]
    start, end = _pick_window(spec)

    df = get_incidents(city_key, start, end, view="comparable", limit=200)

    assert isinstance(df, pd.DataFrame), f"{city_key}: expected DataFrame"
    # Every std_* column must exist, even on an empty frame.
    for col in STD_COLUMNS:
        assert col in df.columns, f"{city_key}: missing column {col!r}"

    # If we did get rows, provenance must be populated.
    if len(df) > 0:
        assert (df["std_city"] == city_key).all(), f"{city_key}: provenance mismatch"
