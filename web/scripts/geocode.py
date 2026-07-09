#!/usr/bin/env python3
"""Address → (lat, lng) geocoder for citycrimemap.us.

For cities that publish incident records without coordinates (Boston,
Dallas, Providence, New Orleans), we resolve the published address to
a lat/lng via the U.S. Census Bureau geocoder. The Census Geocoder is
free, requires no API key, and accepts batches up to 10,000 rows per
request.

San Antonio is *not* handled here — SAPD redacts all three of its
incident datasets (Offenses, Arrests, Calls for Service) to ZIP only,
so there is no street address to geocode. ZIP centroids on a crime
map would imply precision we don't have.

This module is web/-only. It does not belong in the tidycop library
half — the library stays upstream-parity and city-agnostic, and the
upstream R `tidycops` has no geocoder.

Endpoints used
--------------
- Batch: https://geocoding.geo.census.gov/geocoder/locations/addressbatch
  (free, no key, up to 10k addresses per POST, returns CSV)

Address normalization
---------------------
Boston's `BLOCK` field looks like "0 BLOCK  VICTORY RD" or
"1400 BLOCK  RIVER ST". The Census geocoder can't match
"N BLOCK <STREET>" phrasing, so we rewrite to "<N> <STREET>" before
sending. The block midpoint is good enough for a map dot, and matches
the redaction the police publish.

Intersections ("BEACON ST & RALEIGH ST") are sent as-is to the
onelineaddress endpoint — Census handles "X AND Y" reasonably for
common street pairs.

Cache
-----
Results are cached in a sqlite db keyed by (city, normalized_address).
Cache survives across runs; weekly refreshes typically only need to
geocode the small number of net-new block addresses.
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import sys
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

CENSUS_BATCH_URL = (
    "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
)
CENSUS_BENCHMARK = "Public_AR_Current"
CENSUS_BATCH_LIMIT = 10_000
HTTP_TIMEOUT = 600  # batch endpoint can take 1-3 minutes for 10k rows

DEFAULT_CACHE_PATH = Path(__file__).parent.parent / "data" / "geocode_cache.sqlite"

# Match "0 BLOCK <street>", "1400 BLOCK  RIVER ST", etc.
# Captures the number and the street.
_BLOCK_RE = re.compile(r"^\s*(\d+)\s*BLOCK\s+(.+?)\s*$", re.IGNORECASE)
# Match intersections: "FOO ST & BAR ST", "FOO ST / BAR ST", "FOO AND BAR".
_INTERSECTION_RE = re.compile(r"\s*(?:&|/|\bAND\b)\s*", re.IGNORECASE)
# NOPD block anonymization: "027XX Canal St", "039XX N Claiborne Av".
# The trailing "XX" replaces the last two digits of the hundred-block.
# Rewrite "NNNXX" → the start of that block ("NNN00", stripped of
# leading zeros so Census sees a clean number).
_NOPD_BLOCK_RE = re.compile(r"^\s*0*(\d{1,4})XX\s+(.+?)\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class CityGeocodeConfig:
    """Per-city geocoder config: what state to send, defaults, etc."""

    city: str  # matching tidycop registry key, e.g. "boston"
    state: str  # 2-letter, e.g. "MA"
    city_label: str  # how the city appears in mailing addresses, e.g. "BOSTON"


# Cities the frontend wants geocoded. Add to this dict as new cities ship.
CITY_CONFIGS: dict[str, CityGeocodeConfig] = {
    "boston": CityGeocodeConfig(city="boston", state="MA", city_label="BOSTON"),
    "dallas": CityGeocodeConfig(city="dallas", state="TX", city_label="DALLAS"),
    "providence": CityGeocodeConfig(
        city="providence", state="RI", city_label="PROVIDENCE"
    ),
    "new_orleans": CityGeocodeConfig(
        city="new_orleans", state="LA", city_label="NEW ORLEANS"
    ),
    "kansas_city": CityGeocodeConfig(
        city="kansas_city", state="MO", city_label="KANSAS CITY"
    ),
}


# ─────────────────────────── normalization ────────────────────────────


def normalize_address(raw: str | None) -> str | None:
    """Turn an upstream address string into a Census-friendly form.

    Returns None if the address is unusable (None, empty, just a place
    name like "GREAT BREWSTER ISLAND").

    Examples
    --------
    >>> normalize_address("0 BLOCK  VICTORY RD")
    '1 VICTORY RD'
    >>> normalize_address("1400 BLOCK MAIN ST")
    '1400 MAIN ST'
    >>> normalize_address("BEACON ST & RALEIGH ST")
    'BEACON ST AND RALEIGH ST'
    >>> normalize_address(None) is None
    True
    """
    if not raw:
        return None
    s = re.sub(r"\s+", " ", str(raw)).strip().upper()
    if not s:
        return None

    # "1400 BLOCK MAIN ST" → "1400 MAIN ST"
    m = _BLOCK_RE.match(s)
    if m:
        number = m.group(1)
        street = m.group(2).strip()
        # A "0 BLOCK" address is the low end of the street; treat it as
        # number 1 so the Census matcher has something to lock onto.
        if number == "0":
            number = "1"
        return f"{number} {street}"

    # NOPD "027XX Canal St" → "2700 CANAL ST". The XX represents the
    # unknown last two digits of the hundred-block; anchor to the low
    # end so Census maps to the correct block.
    m = _NOPD_BLOCK_RE.match(s)
    if m:
        hundreds = m.group(1)
        street = m.group(2).strip()
        # "0" hundreds → "1" so we don't send "00 STREET".
        base = int(hundreds) * 100
        if base == 0:
            base = 1
        return f"{base} {street}"

    # Intersections: normalize separators to " AND "
    if _INTERSECTION_RE.search(s):
        parts = [p.strip() for p in _INTERSECTION_RE.split(s) if p.strip()]
        if len(parts) >= 2:
            return " AND ".join(parts[:2])

    # Looks like a street with a leading number? Pass through.
    if re.match(r"^\d+\s+\w", s):
        return s

    # Place name or unparseable — give up.
    return None


def build_oneline(normalized: str, cfg: CityGeocodeConfig, zip_code: str | None) -> str:
    """Render a normalized address as the single-line form Census expects.

    "1400 MAIN ST" + Boston MA + 02125 → "1400 MAIN ST, BOSTON, MA, 02125"
    """
    parts = [normalized, cfg.city_label, cfg.state]
    if zip_code:
        z = str(zip_code).strip()
        if z:
            parts.append(z)
    return ", ".join(parts)


# ───────────────────────────── cache ──────────────────────────────────


def _open_cache(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS geocode_cache (
            city           TEXT NOT NULL,
            normalized     TEXT NOT NULL,
            zip_code       TEXT,
            lat            REAL,
            lng            REAL,
            match_quality  TEXT,
            matched_addr   TEXT,
            found_at       TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (city, normalized, zip_code)
        )
        """
    )
    return conn


# Sentinel returned by _cache_get when the cache has recorded a confirmed
# Census non-match. Distinct from None (cache miss — not yet seen).
_CACHED_MISS = object()


def _cache_get(
    conn: sqlite3.Connection, city: str, normalized: str, zip_code: str | None
):
    """Return (lat, lng), _CACHED_MISS, or None.

    - tuple: cached hit, use these coords.
    - _CACHED_MISS: we asked Census before and it said no — don't ask again.
    - None: never asked Census for this address.
    """
    row = conn.execute(
        "SELECT lat, lng FROM geocode_cache "
        "WHERE city = ? AND normalized = ? AND zip_code IS ?",
        (city, normalized, zip_code or None),
    ).fetchone()
    if not row:
        return None
    lat, lng = row
    if lat is None or lng is None:
        return _CACHED_MISS
    return (lat, lng)


def _cache_put(
    conn: sqlite3.Connection,
    city: str,
    normalized: str,
    zip_code: str | None,
    lat: float | None,
    lng: float | None,
    match_quality: str | None,
    matched_addr: str | None,
) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO geocode_cache
            (city, normalized, zip_code, lat, lng, match_quality, matched_addr)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (city, normalized, zip_code or None, lat, lng, match_quality, matched_addr),
    )


# ───────────────────────── Census batch call ──────────────────────────


def _post_batch(rows: list[tuple[str, str]]) -> list[dict]:
    """POST a chunk of (unique_id, oneline) rows to Census batch geocoder.

    Returns parsed records: {id, match_status, match_quality, matched_addr,
    lat, lng}. A non-match record has lat/lng = None.

    The batch endpoint expects a CSV upload with no header and columns:
        Unique ID, Street address, City, State, ZIP
    Because we have already prebaked the full address into one string,
    we put the whole thing in the "Street address" column and leave the
    other columns empty — Census still parses it. (This is the same
    trick the onelineaddress endpoint uses internally.)
    """
    if not rows:
        return []

    buf = io.StringIO()
    writer = csv.writer(buf)
    for uid, oneline in rows:
        writer.writerow([uid, oneline, "", "", ""])
    payload = buf.getvalue().encode("utf-8")

    resp = requests.post(
        CENSUS_BATCH_URL,
        files={"addressFile": ("addresses.csv", payload, "text/csv")},
        data={"benchmark": CENSUS_BENCHMARK},
        timeout=HTTP_TIMEOUT,
    )
    resp.raise_for_status()

    # Response CSV columns:
    #   id, input_addr, match_status, match_type, matched_addr,
    #   coordinates ("lon,lat"), tigerline_id, side
    reader = csv.reader(io.StringIO(resp.text))
    out: list[dict] = []
    for row in reader:
        if not row:
            continue
        # Pad short rows defensively.
        row = row + [""] * (8 - len(row))
        uid, input_addr, status, mtype, matched, coords = row[:6]
        lat = lng = None
        if coords and "," in coords:
            try:
                lng_s, lat_s = coords.split(",", 1)
                lng = float(lng_s)
                lat = float(lat_s)
            except ValueError:
                pass
        out.append(
            {
                "id": uid,
                "input": input_addr,
                "match_status": status,
                "match_quality": mtype,
                "matched_addr": matched,
                "lat": lat,
                "lng": lng,
            }
        )
    return out


# ────────────────────────── public API ────────────────────────────────


def geocode_addresses(
    city: str,
    addresses: Iterable[tuple[str | None, str | None]],
    *,
    cache_path: Path = DEFAULT_CACHE_PATH,
    verbose: bool = True,
) -> dict[tuple[str, str | None], tuple[float, float]]:
    """Geocode a stream of (raw_address, zip_code) pairs for one city.

    Returns a dict keyed by (normalized_address, zip_code) mapping to
    (lat, lng). Missing / unmatched addresses are simply absent from
    the dict.

    Cache-first: any (city, normalized, zip) seen before is served
    from sqlite. Only net-new addresses go to Census.
    """
    cfg = CITY_CONFIGS.get(city)
    if cfg is None:
        raise ValueError(
            f"No geocode config for city {city!r}. Add to CITY_CONFIGS."
        )

    # 1. Normalize and dedupe.
    wanted: dict[tuple[str, str | None], None] = {}
    for raw, zc in addresses:
        norm = normalize_address(raw)
        if norm is None:
            continue
        zc_norm = (str(zc).strip() if zc else None) or None
        wanted[(norm, zc_norm)] = None

    if verbose:
        print(f"[geocode] {city}: {len(wanted)} unique normalized addresses")

    results: dict[tuple[str, str | None], tuple[float, float]] = {}
    misses: list[tuple[str, str | None]] = []

    # 2. Check cache.
    with closing(_open_cache(cache_path)) as conn:
        for key in wanted:
            norm, zc = key
            hit = _cache_get(conn, city, norm, zc)
            if hit is None:
                misses.append(key)  # never asked Census
            elif hit is _CACHED_MISS:
                pass  # Census said no last time — don't ask again
            else:
                results[key] = hit

        if verbose:
            print(
                f"[geocode] {city}: cache hits {len(results)}, "
                f"misses {len(misses)}"
            )

        if not misses:
            return results

        # 3. Batch unresolved addresses through Census.
        # Census limit is 10k; we chunk just in case future cities push past it.
        for i in range(0, len(misses), CENSUS_BATCH_LIMIT):
            chunk = misses[i : i + CENSUS_BATCH_LIMIT]
            rows: list[tuple[str, str]] = []
            id_to_key: dict[str, tuple[str, str | None]] = {}
            for idx, key in enumerate(chunk):
                norm, zc = key
                uid = f"r{i + idx}"
                rows.append((uid, build_oneline(norm, cfg, zc)))
                id_to_key[uid] = key

            if verbose:
                print(
                    f"[geocode] {city}: POST batch "
                    f"{i + 1}..{i + len(rows)} of {len(misses)}"
                )
            t0 = time.time()
            try:
                parsed = _post_batch(rows)
            except requests.RequestException as exc:
                print(f"[geocode] {city}: batch failed: {exc}", file=sys.stderr)
                continue
            if verbose:
                print(
                    f"[geocode] {city}: batch returned "
                    f"{len(parsed)} records in {time.time() - t0:.1f}s"
                )

            new_hits = 0
            for rec in parsed:
                key = id_to_key.get(rec["id"])
                if key is None:
                    continue
                norm, zc = key
                if rec["lat"] is not None and rec["lng"] is not None:
                    results[key] = (rec["lat"], rec["lng"])
                    new_hits += 1
                # Cache both hits and misses (None lat/lng) so we don't
                # keep re-asking Census about addresses it can't match.
                _cache_put(
                    conn,
                    city,
                    norm,
                    zc,
                    rec["lat"],
                    rec["lng"],
                    rec["match_quality"] or None,
                    rec["matched_addr"] or None,
                )
            conn.commit()
            if verbose:
                print(
                    f"[geocode] {city}: batch matched {new_hits} / {len(rows)}"
                )

    return results


# ────────────────────────────── CLI ───────────────────────────────────


def _cli_main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Geocode addresses for a city using the Census batch API."
    )
    parser.add_argument(
        "--city",
        required=True,
        help="City key (one of: " + ", ".join(sorted(CITY_CONFIGS)) + ")",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=21,
        help="Window in days for the sample (default 21).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=2000,
        help="Max upstream rows to pull (default 2000).",
    )
    parser.add_argument(
        "--cache",
        default=str(DEFAULT_CACHE_PATH),
        help="sqlite cache path",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(Path(__file__).parent))
    from datetime import date, timedelta

    from tidycop import get_incidents  # noqa: E402

    end = date.today()
    start = end - timedelta(days=args.days)
    print(f"[geocode-cli] fetch {args.city} {start}..{end} (limit {args.limit})")
    df = get_incidents(
        args.city,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        limit=args.limit,
        classify_spotcrime=True,
    )
    print(f"[geocode-cli] {len(df)} rows")

    addrs = list(
        zip(
            df.get("std_address", []).tolist() if "std_address" in df.columns else [],
            df.get("std_zip_code", []).tolist() if "std_zip_code" in df.columns else [],
        )
    )
    results = geocode_addresses(
        args.city, addrs, cache_path=Path(args.cache), verbose=True
    )
    matched = len(results)
    total_addresses = sum(1 for a, _ in addrs if a)
    print(
        f"[geocode-cli] {args.city}: matched {matched} unique addresses "
        f"out of {total_addresses} non-null rows ({len(df)} total)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(_cli_main())
