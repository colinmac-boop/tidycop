"""Live smoke test against the real Pittsburgh (WPRDC) CKAN endpoint.

Opt-in: set TIDYCOP_LIVE_CKAN=1 to enable. Skipped by default.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from tidycop.platform.ckan import CKANFetcher
from tidycop.registry import get_city_spec

LIVE = os.environ.get("TIDYCOP_LIVE_CKAN") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE, reason="set TIDYCOP_LIVE_CKAN=1 to run live network smoke tests"
)


def test_live_pittsburgh_smoke():
    city = get_city_spec("pittsburgh")
    source = city.sources[0]
    assert source.provider == "ckan"

    fetcher = CKANFetcher()
    # Pittsburgh's WPRDC feed starts 2024-01-01 (rolling window).
    # Pick a one-week slice in early 2024 to keep this small but populated.
    rows = fetcher.fetch(
        source,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 7),
        limit=500,
    )

    assert isinstance(rows, list)
    assert len(rows) > 0, "Pittsburgh live fetch returned 0 rows"

    sample = rows[0]
    assert source.date_field in sample, (
        f"missing date_field {source.date_field!r} in response; " f"keys={list(sample.keys())[:10]}"
    )
    # std_incident_number maps to "Report_Number" (single string).
    inc_no = source.field_map.get("std_incident_number")
    assert isinstance(inc_no, str)
    present = sum(1 for r in rows if r.get(inc_no))
    assert present > 0, f"no rows had a populated {inc_no!r}"
