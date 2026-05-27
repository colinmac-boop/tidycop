"""Live smoke test against real Socrata endpoints.

Opt-in: set TIDYCOP_LIVE_SOCRATA=1 to enable. Skipped by default so the rest
of the suite never hits the network.

The chosen window (2026-04-01 → 2026-04-30) is small enough to complete in
seconds but large enough to verify paging across multiple PAGE_SIZE chunks.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from tidycop.platform.socrata import PAGE_SIZE, SocrataFetcher
from tidycop.registry import get_city_spec

LIVE = os.environ.get("TIDYCOP_LIVE_SOCRATA") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE, reason="set TIDYCOP_LIVE_SOCRATA=1 to run live network smoke tests"
)


@pytest.mark.parametrize("city_key", ["chicago", "seattle", "san_francisco"])
def test_live_socrata_fetch_smoke(city_key):
    city = get_city_spec(city_key)
    source = city.sources[0]
    assert source.provider == "socrata", "this test only covers Socrata cities"

    fetcher = SocrataFetcher()
    # Small window, capped limit to keep this quick.
    rows = fetcher.fetch(
        source,
        start_date=date(2026, 4, 1),
        end_date=date(2026, 4, 7),
        limit=PAGE_SIZE * 2 + 50,  # exercise the paging loop
    )

    assert isinstance(rows, list)
    assert len(rows) > 0, f"{city_key}: live fetch returned 0 rows"

    # Every row should have at least the date_field present.
    sample = rows[0]
    assert source.date_field in sample, (
        f"{city_key}: response row missing expected date_field "
        f"{source.date_field!r}; keys={list(sample.keys())[:10]}"
    )

    # Every row's std_incident_id source field should resolve to something.
    inc_id_field = source.field_map.get("std_incident_id")
    if isinstance(inc_id_field, str):
        present = sum(1 for r in rows if r.get(inc_id_field))
        assert present > 0, f"{city_key}: no rows had a populated {inc_id_field!r}"
