"""Smoke tests for web/scripts/geocode.py.

These are *web*-side tests, not part of the tidycop library test suite.
Run with:  .venv/bin/python -m pytest web/tests/ -q

Covers:
- normalize_address: BPD "N BLOCK <STREET>" rewrite, intersections,
  unparseable garbage.
- build_oneline: Census-friendly single-line address composition.
- geocode_addresses: cache layer + Census batch end-to-end with the
  HTTP call mocked. Verifies that cached hits are not re-requested.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

# Make web/scripts importable.
WEB_SCRIPTS = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(WEB_SCRIPTS))

import geocode  # noqa: E402


# ─────────────────────── normalize_address ────────────────────────────


def test_normalize_block_zero():
    # "0 BLOCK" becomes "1 STREET" so Census has a numeric anchor.
    assert geocode.normalize_address("0 BLOCK  VICTORY RD") == "1 VICTORY RD"


def test_normalize_block_nonzero():
    assert geocode.normalize_address("1400 BLOCK  MAIN ST") == "1400 MAIN ST"


def test_normalize_block_collapses_whitespace():
    assert geocode.normalize_address("100   BLOCK    MASSACHUSETTS  AVE") == "100 MASSACHUSETTS AVE"


def test_normalize_intersection_ampersand():
    assert geocode.normalize_address("BEACON ST & RALEIGH ST") == "BEACON ST AND RALEIGH ST"


def test_normalize_intersection_slash():
    assert geocode.normalize_address("WINTER PL / WINTER ST") == "WINTER PL AND WINTER ST"


def test_normalize_intersection_word_and():
    assert geocode.normalize_address("CENTRE ST AND WHITCOMB AVE") == "CENTRE ST AND WHITCOMB AVE"


def test_normalize_passthrough_standard_address():
    # A real street address with no "BLOCK" wrapper passes through.
    assert geocode.normalize_address("42 BAKER ST") == "42 BAKER ST"


def test_normalize_rejects_place_name():
    assert geocode.normalize_address("GREAT BREWSTER ISLAND") is None


def test_normalize_rejects_none():
    assert geocode.normalize_address(None) is None


def test_normalize_rejects_empty():
    assert geocode.normalize_address("") is None
    assert geocode.normalize_address("   ") is None


# NOPD block anonymization (New Orleans): "NNNXX <STREET>".
def test_normalize_nopd_block_standard():
    assert geocode.normalize_address("027XX Canal St") == "2700 CANAL ST"


def test_normalize_nopd_block_with_direction():
    assert (
        geocode.normalize_address("039XX N Claiborne Av") == "3900 N CLAIBORNE AV"
    )


def test_normalize_nopd_block_zero():
    # "000XX" is the low end of the street; treat as house #1.
    assert geocode.normalize_address("000XX Foo St") == "1 FOO ST"


# ────────────────────────── build_oneline ─────────────────────────────


def test_build_oneline_with_zip():
    cfg = geocode.CITY_CONFIGS["boston"]
    assert (
        geocode.build_oneline("1400 MAIN ST", cfg, "02125")
        == "1400 MAIN ST, BOSTON, MA, 02125"
    )


def test_build_oneline_without_zip():
    cfg = geocode.CITY_CONFIGS["boston"]
    assert (
        geocode.build_oneline("1400 MAIN ST", cfg, None)
        == "1400 MAIN ST, BOSTON, MA"
    )


# ────────────────────── geocode_addresses ─────────────────────────────


def test_geocode_addresses_uses_cache_and_batches(tmp_path):
    cache_path = tmp_path / "cache.sqlite"

    # Pre-seed cache with one known hit so we can verify the cache layer
    # short-circuits a second request for the same address.
    with geocode._open_cache(cache_path) as conn:
        geocode._cache_put(
            conn,
            city="boston",
            normalized="1 ABBOT ST",
            zip_code="02124",
            lat=42.29764,
            lng=-71.08692,
            match_quality="Exact",
            matched_addr="1 ABBOT ST, BOSTON, MA, 02124",
        )
        conn.commit()

    addrs = [
        ("0 BLOCK ABBOT ST", "02124"),   # cached
        ("1400 BLOCK MAIN ST", "02125"), # uncached → Census batch
        (None, None),                     # skipped (no address)
        ("0 BLOCK ABBOT ST", "02124"),   # duplicate of cached
    ]

    fake_batch_response = [
        {
            "id": "r0",
            "input": "1400 MAIN ST, BOSTON, MA, 02125",
            "match_status": "Match",
            "match_quality": "Exact",
            "matched_addr": "1400 MAIN ST, BOSTON, MA, 02125",
            "lat": 42.30000,
            "lng": -71.07000,
        }
    ]

    with patch.object(geocode, "_post_batch", return_value=fake_batch_response) as mocked:
        results = geocode.geocode_addresses(
            "boston", addrs, cache_path=cache_path, verbose=False
        )

    # Exactly one batch POST despite the duplicate input.
    assert mocked.call_count == 1
    # The batch payload contained only the *uncached* unique address.
    posted_rows = mocked.call_args.args[0]
    assert len(posted_rows) == 1
    assert posted_rows[0][1].startswith("1400 MAIN ST, BOSTON, MA, 02125")

    # Both unique addresses end up resolved in the results dict.
    assert results[("1 ABBOT ST", "02124")] == (42.29764, -71.08692)
    assert results[("1400 MAIN ST", "02125")] == (42.30000, -71.07000)
    # The (None, None) row never enters the results dict.
    assert all(k[0] is not None for k in results.keys())


def test_geocode_addresses_caches_misses(tmp_path):
    """A Census non-match is cached so we don't re-ask on the next refresh."""
    cache_path = tmp_path / "cache.sqlite"

    addrs = [("0 BLOCK NONEXISTENT WAY", "02199")]
    miss_response = [
        {
            "id": "r0",
            "input": "1 NONEXISTENT WAY, BOSTON, MA, 02199",
            "match_status": "No_Match",
            "match_quality": "",
            "matched_addr": "",
            "lat": None,
            "lng": None,
        }
    ]

    with patch.object(geocode, "_post_batch", return_value=miss_response) as mocked:
        results = geocode.geocode_addresses(
            "boston", addrs, cache_path=cache_path, verbose=False
        )
    assert results == {}
    assert mocked.call_count == 1

    # Second call: same address. No new HTTP. Still no result.
    with patch.object(geocode, "_post_batch", return_value=miss_response) as mocked2:
        results2 = geocode.geocode_addresses(
            "boston", addrs, cache_path=cache_path, verbose=False
        )
    assert results2 == {}
    assert mocked2.call_count == 0  # cache short-circuit


def test_geocode_addresses_rejects_unknown_city(tmp_path):
    cache_path = tmp_path / "cache.sqlite"
    try:
        geocode.geocode_addresses(
            "atlantis", [("1 SUNKEN ST", None)], cache_path=cache_path
        )
    except ValueError as exc:
        assert "atlantis" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown city")
