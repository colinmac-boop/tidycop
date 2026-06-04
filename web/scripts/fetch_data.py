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

OUTPUT_DIR = Path(__file__).parent.parent / "data"
MAX_INCIDENTS_PER_CITY = 1500  # cap payload so /data/*.json stays browser-friendly


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
    return {
        "id": str(row.get("std_incident_id") or row.get("std_source_record_id") or ""),
        "lat": round(latf, 6),
        "lng": round(lngf, 6),
        "datetime": dt_str,
        "description": (row.get("std_offense_description") or "").strip() or None,
        "address": (row.get("std_address") or "").strip() or None,
        "category": row.get("std_spotcrime_category") or None,
    }


def fetch_city(city: dict) -> dict:
    end = date.today()
    start = end - timedelta(days=city["window_days"])
    print(f"[fetch] {city['key']}: {start} → {end} ({city['window_days']}d)")
    df = get_incidents(
        city["key"],
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        classify_spotcrime=True,
    )
    print(f"[fetch] {city['key']}: {len(df)} raw rows")

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
