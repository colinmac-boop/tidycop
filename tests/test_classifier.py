"""Tests for tidycop's SpotCrime classifier integration.

The classifier itself lives in the separate ``tidycop-spotcrime`` package
(extracted in v0.3.0 to honor the city-agnostic library boundary — see
AGENTS.md "Hard Boundary"). What stays here:

1. **Registry coverage** — every MVP city ships a valid
   ``spotcrime_category_map`` in ``registry/cities.yaml``. The map is
   data living in this repo, so it gets validated here.
2. **Soft-import seam** — ``get_incidents(..., classify_spotcrime=True)``
   transparently calls ``tidycop_spotcrime.classify_frame`` when the
   extension package is installed, and raises a clear ``ImportError``
   when it isn't.
"""

from __future__ import annotations

import sys
from datetime import date
from unittest.mock import patch

import pandas as pd
import pytest

from tidycop import get_incidents
from tidycop.registry import _reset_cache, get_city_spec


# Pull the canonical category tuple from the extension package. This test
# file imports it for the registry-coverage assertions; if the extension
# isn't installed, those parametrized tests are skipped (the integration
# tests below cover the missing-extension path explicitly).
try:
    from tidycop_spotcrime import SPOTCRIME_CATEGORIES
    HAS_SPOTCRIME_EXT = True
except ImportError:  # pragma: no cover — exercised only on bare installs
    SPOTCRIME_CATEGORIES = ()
    HAS_SPOTCRIME_EXT = False


# ---------------------------------------------------------------------------
# Registry coverage: 5 MVP cities ship a SpotCrime map
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not HAS_SPOTCRIME_EXT,
    reason="tidycop-spotcrime not installed; classifier-side validation skipped",
)
@pytest.mark.parametrize(
    "city", ["chicago", "seattle", "san_francisco", "detroit", "pittsburgh"]
)
def test_mvp_cities_have_spotcrime_map(city: str):
    _reset_cache()
    spec = get_city_spec(city)
    src = spec.sources[0]
    assert src.spotcrime_category_map, f"{city}: missing spotcrime_category_map"
    # All targets must be in the 8 valid categories.
    for native, target in src.spotcrime_category_map.items():
        assert target in SPOTCRIME_CATEGORIES, (
            f"{city}: {native!r} maps to invalid {target!r}"
        )


@pytest.mark.skipif(
    not HAS_SPOTCRIME_EXT,
    reason="tidycop-spotcrime not installed; classifier-side validation skipped",
)
def test_mvp_cities_cover_core_buckets():
    """Every MVP city should at least cover Theft, Robbery, Assault, Burglary."""
    _reset_cache()
    required = {"Theft", "Robbery", "Assault", "Burglary"}
    for city in ("chicago", "seattle", "san_francisco", "detroit", "pittsburgh"):
        spec = get_city_spec(city)
        covered = set(spec.sources[0].spotcrime_category_map.values())
        missing = required - covered
        assert not missing, f"{city}: missing core buckets {missing}"


# ---------------------------------------------------------------------------
# get_incidents() integration — soft-import seam
# ---------------------------------------------------------------------------


class _StubFetcher:
    def __init__(self, rows):
        self.rows = rows

    def fetch(self, source, start_date, end_date, *, limit=1000):
        return list(self.rows)


def _chicago_raw(primary_types):
    return [
        {
            "id": f"id{i}",
            "case_number": f"JZ{i:05d}",
            "date": "2026-04-01T12:00:00.000",
            "iucr": "0820",
            # description is intentionally a non-mappable label so the
            # fallback path in classify_row doesn't accidentally rescue
            # categories the test wants to be unmapped.
            "description": "GENERIC OFFENSE",
            "primary_type": pt,
            "block": "001XX N STATE ST",
            "community_area": "8",
            "district": "001",
            "beat": "0111",
            "latitude": "41.0",
            "longitude": "-87.0",
        }
        for i, pt in enumerate(primary_types)
    ]


def test_get_incidents_classify_spotcrime_off_by_default():
    fetcher = _StubFetcher(_chicago_raw(["THEFT", "BATTERY"]))
    df = get_incidents("chicago", date(2026, 4, 1), date(2026, 4, 1), fetcher=fetcher)
    assert "std_spotcrime_category" not in df.columns


@pytest.mark.skipif(
    not HAS_SPOTCRIME_EXT,
    reason="tidycop-spotcrime not installed; end-to-end classify path skipped",
)
def test_get_incidents_classify_spotcrime_on():
    fetcher = _StubFetcher(_chicago_raw(["THEFT", "ROBBERY", "ARSON", "KIDNAPPING"]))
    df = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        fetcher=fetcher,
        classify_spotcrime=True,
    )
    assert "std_spotcrime_category" in df.columns
    # Tolerate pandas 2.x None vs 3.x NaN for the unmapped slot.
    got = [
        None if (v is None or (isinstance(v, float) and pd.isna(v))) else v
        for v in df["std_spotcrime_category"]
    ]
    assert got == ["Theft", "Robbery", "Arson", None]


@pytest.mark.skipif(
    not HAS_SPOTCRIME_EXT,
    reason="tidycop-spotcrime not installed; end-to-end classify path skipped",
)
def test_get_incidents_classify_fatal_shootings_collapse_to_shooting():
    """Pre-2026-05-26 we had a 'Homicide' bucket; now fatal shootings → Shooting."""
    fetcher = _StubFetcher(_chicago_raw(["HOMICIDE"]))
    df = get_incidents(
        "chicago",
        date(2026, 4, 1),
        date(2026, 4, 1),
        fetcher=fetcher,
        classify_spotcrime=True,
    )
    assert df["std_spotcrime_category"].iat[0] == "Shooting"


def test_get_incidents_classify_spotcrime_without_extension_raises():
    """When tidycop-spotcrime isn't importable, classify_spotcrime=True must
    raise a clear ImportError pointing at the install command.

    We simulate the missing-extension case by stubbing the module out of
    sys.modules and blocking its re-import — this exercises the
    soft-import branch in tidycop.core regardless of whether the package
    is actually installed in this venv.
    """
    import builtins

    fetcher = _StubFetcher(_chicago_raw(["THEFT"]))

    # Make `import tidycop_spotcrime` fail inside get_incidents.
    blocked = {k: v for k, v in sys.modules.items() if k.startswith("tidycop_spotcrime")}
    for k in blocked:
        sys.modules.pop(k)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "tidycop_spotcrime" or name.startswith("tidycop_spotcrime."):
            raise ImportError(f"No module named {name!r} (simulated)")
        return real_import(name, *args, **kwargs)

    try:
        with patch("builtins.__import__", side_effect=fake_import):
            with pytest.raises(ImportError, match="tidycop-spotcrime"):
                get_incidents(
                    "chicago",
                    date(2026, 4, 1),
                    date(2026, 4, 1),
                    fetcher=fetcher,
                    classify_spotcrime=True,
                )
    finally:
        # Restore anything we removed so other tests can use the extension.
        for k, v in blocked.items():
            sys.modules[k] = v
