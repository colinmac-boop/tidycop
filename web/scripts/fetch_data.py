#!/usr/bin/env python3
"""Fetch incidents for the five cities via tidycop and emit JSON for the site.

Outputs one file per city under citymaps/data/<slug>.json with the shape:

  {
    "city": "Chicago",
    "slug": "chicago",
    "state_abbrev": "IL",
    "generated_at": "2026-05-31T22:00:00Z",
    "window_days": 45,
    "row_count": 1000,
    "category_counts": {"Theft": 328, ...},
    "incidents": [
      {
        "id": "13xxxxxx",
        "lat": 41.85,
        "lng": -87.63,
        "datetime": "2026-05-28T03:14:00Z",
        "description": "THEFT FROM MOTOR VEHICLE",
        "address": "012XX N MICHIGAN AVE",
        "category": "Theft"
      },
      ...
    ]
  }

Run with the tidycop venv:
  ~/Projects/tidycop/.venv/bin/python citymaps/scripts/fetch_data.py
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from cities import CITIES  # type: ignore

# Make tidycop importable when running from the citymaps/scripts dir.
sys.path.insert(0, str(Path(__file__).parent))

from tidycop import get_incidents  # noqa: E402

from geocode import CITY_CONFIGS as GEOCODE_CITIES, geocode_addresses  # noqa: E402

OUTPUT_DIR = Path(__file__).parent.parent / "data"
MAX_INCIDENTS_PER_CITY = 1500  # cap payload so /data/*.json stays browser-friendly

# Downstream registry overlay for cities not in upstream R tidycops.
# See AGENTS.md § Hard Boundary: cities like Baltimore and Los Angeles
# that aren't in upstream `incident_registry.R` can still ship on the
# frontend by living in this overlay and being requested with
# `registry_path=`. Boundary rule: NEVER move entries from here into
# `registry/cities.yaml`.
REGISTRY_OVERLAY = Path(__file__).parent.parent / "registry_overlay.yaml"


def normalize_incident(row: dict) -> dict | None:
    import math
    lat = row.get("std_latitude") if row.get("std_latitude") is not None else row.get("std_lat")
    lng = row.get("std_longitude") if row.get("std_longitude") is not None else row.get("std_lng")
    if lat is None or lng is None:
        return None
    try:
        latf = float(lat)
        lngf = float(lng)
    except (TypeError, ValueError):
        return None
    if math.isnan(latf) or math.isnan(lngf):
        return None
    if latf == 0 and lngf == 0:
        return None  # null-island junk
    # Sentinel values from portals that hide sensitive locations
    # (Seattle SPD emits (-1, -1) for redacted-address rows). Anything
    # obviously outside US+territories bounds is also a lost cause for
    # a US-only crime map.
    if not (17.0 < latf < 72.0 and -180.0 < lngf < -60.0):
        return None
    dt = row.get("std_incident_date") or row.get("std_reported_date") or row.get("std_datetime")
    dt_str = None
    if dt is not None:
        try:
            if hasattr(dt, "isoformat"):
                dt_str = dt.isoformat()
            elif isinstance(dt, float) and math.isnan(dt):
                dt_str = None
            else:
                dt_str = str(dt)
        except Exception:
            dt_str = str(dt)
    # Neighborhood is optional — only 12 of 16 live cities carry it upstream.
    # We keep the raw label as-is (Chicago "08A", DC "Cluster 25", SF
    # "Mission") and let the frontend slugify + display it.
    hood_raw = row.get("std_neighborhood")
    if hood_raw is None or (isinstance(hood_raw, float) and math.isnan(hood_raw)):
        hood = None
    else:
        hood = str(hood_raw).strip() or None
    return {
        "id": str(row.get("std_incident_id") or row.get("std_source_record_id") or ""),
        "lat": round(latf, 6),
        "lng": round(lngf, 6),
        "datetime": dt_str,
        "description": (row.get("std_offense_description") or "").strip() or None,
        "address": (row.get("std_address") or "").strip() or None,
        "category": row.get("std_spotcrime_category") or None,
        "neighborhood": hood,
    }


def _apply_geocoding(city_key: str, df):
    """For cities with no upstream lat/lng, geocode addresses via Census.

    Mutates ``df`` in place by writing into std_latitude / std_longitude
    for rows whose normalized address matched. Returns the count of rows
    that could not be located (for the honest "N could not be located"
    counter on the page).
    """
    from geocode import normalize_address  # local import keeps this opt-in

    if "std_address" not in df.columns:
        return 0
    addr_iter = zip(
        df["std_address"].tolist(),
        df["std_zip_code"].tolist() if "std_zip_code" in df.columns else [None] * len(df),
    )
    addrs = list(addr_iter)
    results = geocode_addresses(city_key, addrs, verbose=True)

    # Ensure the std_latitude/std_longitude columns exist.
    if "std_latitude" not in df.columns:
        df["std_latitude"] = None
    if "std_longitude" not in df.columns:
        df["std_longitude"] = None

    located = 0
    unlocated = 0
    for idx, (raw, zc) in enumerate(addrs):
        norm = normalize_address(raw)
        if norm is None:
            unlocated += 1
            continue
        zc_norm = (str(zc).strip() if zc else None) or None
        hit = results.get((norm, zc_norm))
        if hit is None:
            unlocated += 1
            continue
        lat, lng = hit
        df.iat[idx, df.columns.get_loc("std_latitude")] = lat
        df.iat[idx, df.columns.get_loc("std_longitude")] = lng
        located += 1
    print(
        f"[geocode] {city_key}: located {located} / {len(addrs)} rows "
        f"({unlocated} could not be located)"
    )
    return unlocated


def fetch_city(city: dict) -> dict:
    end = date.today()
    start = end - timedelta(days=city["window_days"])
    print(f"[fetch] {city['key']}: {start} → {end} ({city['window_days']}d)")
    # Cities with `overlay: True` are downstream-only additions (not in
    # upstream R tidycops) served from web/registry_overlay.yaml.
    fetch_kwargs = dict(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        classify_spotcrime=True,
    )
    if city.get("overlay"):
        fetch_kwargs["registry_path"] = str(REGISTRY_OVERLAY)
    df = get_incidents(city["key"], **fetch_kwargs)
    print(f"[fetch] {city['key']}: {len(df)} raw rows")

    # Optionally drop rows the classifier left Unclassified. Used for
    # cities whose feed is mostly non-criminal admin (boston).
    if city.get("drop_unclassified") and "std_spotcrime_category" in df.columns:
        before = len(df)
        df = df[df["std_spotcrime_category"].notna()].reset_index(drop=True)
        print(
            f"[fetch] {city['key']}: drop_unclassified pruned "
            f"{before - len(df)} rows, {len(df)} remain"
        )

    # Optionally drop rows whose std_offense_description matches a
    # known-admin label. Used for seattle ("Not Reportable to NIBRS")
    # where the feed literally tags admin records but those records
    # would otherwise bloat the Unclassified bucket.
    drop_descs = city.get("drop_descriptions")
    if drop_descs and "std_offense_description" in df.columns:
        before = len(df)
        mask = ~df["std_offense_description"].astype(str).str.casefold().isin(
            {d.casefold() for d in drop_descs}
        )
        df = df[mask].reset_index(drop=True)
        print(
            f"[fetch] {city['key']}: drop_descriptions pruned "
            f"{before - len(df)} rows, {len(df)} remain"
        )

    # Cities without upstream coords get a Census geocoding pass.
    unlocated = 0
    if city["key"] in GEOCODE_CITIES:
        unlocated = _apply_geocoding(city["key"], df)

    # Drop rows with no coordinates first (try std_latitude then std_lat for compat)
    lat_col = "std_latitude" if "std_latitude" in df.columns else ("std_lat" if "std_lat" in df.columns else None)
    lng_col = "std_longitude" if "std_longitude" in df.columns else ("std_lng" if "std_lng" in df.columns else None)
    if lat_col and lng_col:
        df = df.dropna(subset=[lat_col, lng_col])

    # Sort newest first, then cap
    sort_col = None
    for c in ("std_incident_date", "std_reported_date", "std_datetime"):
        if c in df.columns:
            sort_col = c
            break
    if sort_col:
        df = df.sort_values(sort_col, ascending=False)
    df = df.head(MAX_INCIDENTS_PER_CITY)

    incidents: list[dict] = []
    for row in df.to_dict(orient="records"):
        n = normalize_incident(row)
        if n:
            incidents.append(n)

    cat_counts: dict[str, int] = {}
    for inc in incidents:
        cat = inc["category"] or "Unclassified"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1

    return {
        "city": city["name"],
        "slug": city["slug"],
        "state_abbrev": city["state_abbrev"],
        "state_name": city["state_name"],
        "timezone": city["timezone"],
        "map_center": city["map_center"],
        "map_zoom": city["map_zoom"],
        "spotcrime_alerts_url": city["spotcrime_alerts_url"],
        "data_source": city["data_source"],
        "data_source_url": city["data_source_url"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": city["window_days"],
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "row_count": len(incidents),
        "unlocated_count": unlocated,
        "category_counts": dict(sorted(cat_counts.items(), key=lambda kv: -kv[1])),
        "incidents": incidents,
    }


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = []
    for city in CITIES:
        try:
            data = fetch_city(city)
        except Exception as e:  # noqa: BLE001 - we want best-effort per city
            print(f"[fetch] {city['key']}: ERROR {e}", file=sys.stderr)
            continue
        out_path = OUTPUT_DIR / f"{city['slug']}.json"
        out_path.write_text(json.dumps(data, separators=(",", ":")))
        print(f"[fetch] {city['key']}: wrote {out_path.name} ({data['row_count']} incidents)")
        summary.append(
            {
                "slug": city["slug"],
                "name": city["name"],
                "state_abbrev": city["state_abbrev"],
                "spotcrime_alerts_url": city["spotcrime_alerts_url"],
                "row_count": data["row_count"],
                "unlocated_count": data.get("unlocated_count", 0),
                "window_days": city["window_days"],
                "category_counts": data["category_counts"],
                "generated_at": data["generated_at"],
            }
        )
    (OUTPUT_DIR / "_summary.json").write_text(json.dumps({"cities": summary}, indent=2))
    print(f"[fetch] wrote _summary.json with {len(summary)} cities")
    return 0


if __name__ == "__main__":
    sys.exit(main())
