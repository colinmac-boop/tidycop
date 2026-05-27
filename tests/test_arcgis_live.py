"""Live smoke test against the real Detroit ArcGIS endpoint.

Opt-in: set TIDYCOP_LIVE_ARCGIS=1 to enable. Skipped by default.
"""

from __future__ import annotations

import os
from datetime import date

import pytest

from tidycop.platform.arcgis import ArcGISFetcher
from tidycop.registry import get_city_spec

LIVE = os.environ.get("TIDYCOP_LIVE_ARCGIS") == "1"

pytestmark = pytest.mark.skipif(
    not LIVE, reason="set TIDYCOP_LIVE_ARCGIS=1 to run live network smoke tests"
)


def test_live_detroit_smoke():
    city = get_city_spec("detroit")
    source = city.sources[0]
    assert source.provider == "arcgis"

    fetcher = ArcGISFetcher()
    # Detroit's RMS feed dates back to 2016-12-13 — pick a recent-but-historical
    # window that's almost certainly populated. Cap rows to keep this quick.
    rows = fetcher.fetch(
        source,
        start_date=date(2024, 4, 1),
        end_date=date(2024, 4, 7),
        limit=500,
    )

    assert isinstance(rows, list)
    assert len(rows) > 0, "Detroit live fetch returned 0 rows"

    sample = rows[0]
    # Date field is present (epoch ms; schema will convert downstream).
    assert source.date_field in sample
    # std_incident_number maps to "report_number" (single string in field_map).
    inc_no = source.field_map.get("std_incident_number")
    assert isinstance(inc_no, str)
    present = sum(1 for r in rows if r.get(inc_no))
    assert present > 0, f"no rows had a populated {inc_no!r}"
