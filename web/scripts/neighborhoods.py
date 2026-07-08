"""Neighborhood name lookups and slug helpers.

Most cities publish real neighborhood names (Dorchester, Tenderloin,
etc.) which we can display as-is. Two cities publish numeric or
codename identifiers that need a lookup table to be useful to users:

- Chicago publishes ``community_area`` as a number 1-77. This module
  maps those to the official CPD community-area names.
- Washington DC publishes ``NEIGHBORHOOD_CLUSTER`` as "Cluster N".
  We keep the label but the module also exposes a friendlier
  name for use in page titles / meta.

For every other city with hood data the display value is the raw
label, cleaned only by :func:`display_name` (title-case for
ALL-CAPS labels like Seattle's "CAPITOL HILL").

The frontend uses :func:`hood_slug` to turn a hood label into a
URL-safe slug (``/chicago/lakeview``, ``/washington-dc/cluster-2``).
"""
from __future__ import annotations

import re
import unicodedata

# ─── Chicago community areas (1-77) ────────────────────────────────
# Source: https://en.wikipedia.org/wiki/Community_areas_in_Chicago
# and the Chicago Data Portal's community area boundary file.
CHICAGO_COMMUNITY_AREAS = {
    "1": "Rogers Park", "2": "West Ridge", "3": "Uptown", "4": "Lincoln Square",
    "5": "North Center", "6": "Lakeview", "7": "Lincoln Park", "8": "Near North Side",
    "9": "Edison Park", "10": "Norwood Park", "11": "Jefferson Park", "12": "Forest Glen",
    "13": "North Park", "14": "Albany Park", "15": "Portage Park", "16": "Irving Park",
    "17": "Dunning", "18": "Montclare", "19": "Belmont Cragin", "20": "Hermosa",
    "21": "Avondale", "22": "Logan Square", "23": "Humboldt Park", "24": "West Town",
    "25": "Austin", "26": "West Garfield Park", "27": "East Garfield Park", "28": "Near West Side",
    "29": "North Lawndale", "30": "South Lawndale", "31": "Lower West Side", "32": "Loop",
    "33": "Near South Side", "34": "Armour Square", "35": "Douglas", "36": "Oakland",
    "37": "Fuller Park", "38": "Grand Boulevard", "39": "Kenwood", "40": "Washington Park",
    "41": "Hyde Park", "42": "Woodlawn", "43": "South Shore", "44": "Chatham",
    "45": "Avalon Park", "46": "South Chicago", "47": "Burnside", "48": "Calumet Heights",
    "49": "Roseland", "50": "Pullman", "51": "South Deering", "52": "East Side",
    "53": "West Pullman", "54": "Riverdale", "55": "Hegewisch", "56": "Garfield Ridge",
    "57": "Archer Heights", "58": "Brighton Park", "59": "McKinley Park", "60": "Bridgeport",
    "61": "New City", "62": "West Elsdon", "63": "Gage Park", "64": "Clearing",
    "65": "West Lawn", "66": "Chicago Lawn", "67": "West Englewood", "68": "Englewood",
    "69": "Greater Grand Crossing", "70": "Ashburn", "71": "Auburn Gresham", "72": "Beverly",
    "73": "Washington Heights", "74": "Mount Greenwood", "75": "Morgan Park",
    "76": "O'Hare", "77": "Edgewater",
}


def display_name(city_slug: str, hood_raw: str) -> str:
    """Return a display-friendly neighborhood name for a city + raw label.

    - Chicago numeric codes → real neighborhood name
    - ALL-CAPS labels (Seattle, Houston) → Title Case
    - Denver's dashed-lowercase slugs (`five-points`) → Title Case
    - Everything else passes through unchanged
    """
    if not hood_raw or hood_raw == "-":
        return ""
    if city_slug == "chicago":
        return CHICAGO_COMMUNITY_AREAS.get(str(hood_raw), f"Community Area {hood_raw}")
    if city_slug == "denver":
        # Denver publishes slugs like "five-points", "central-park"
        return " ".join(w.capitalize() for w in str(hood_raw).replace("-", " ").split())
    s = str(hood_raw).strip()
    # ALL-CAPS → Title Case (Seattle "CAPITOL HILL", Houston "NORTHSIDE/NORTHLINE")
    if s.isupper() or s == s.upper():
        # Preserve slash-separated segments
        parts = []
        for seg in s.split("/"):
            words = []
            for w in seg.split():
                if w in {"OF", "AND", "THE", "IN", "ON", "AT"}:
                    words.append(w.lower())
                else:
                    words.append(w.capitalize())
            parts.append(" ".join(words))
        s = " / ".join(parts)
    return s


def hood_slug(display: str) -> str:
    """Slugify a hood display name for URLs.

    ``Lincoln Park`` → ``lincoln-park``
    ``South of Market`` → ``south-of-market``
    ``NORTHSIDE/NORTHLINE`` (display "Northside / Northline") → ``northside-northline``
    ``Bayview Hunters Point`` → ``bayview-hunters-point``
    """
    if not display:
        return ""
    # Unicode normalize (strip accents)
    s = unicodedata.normalize("NFKD", display)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    # Replace non-alphanumeric with single hyphens
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


# Cities whose raw hood labels are un-usable or empty. Neighborhood
# pages are skipped for these; the city page still ships.
CITIES_WITHOUT_HOODS = {"gainesville", "hartford", "indianapolis", "rochester"}


def city_supports_hoods(city_slug: str) -> bool:
    return city_slug not in CITIES_WITHOUT_HOODS


def group_incidents_by_hood(city_slug: str, incidents: list[dict]) -> dict[str, dict]:
    """Group incidents by display hood name.

    Returns dict: display_name → {"slug": ..., "incidents": [...], "count": N}
    Only includes hoods with at least 1 incident. Skips the "-" sentinel
    used by Seattle for unknown-neighborhood rows.
    """
    groups: dict[str, dict] = {}
    for inc in incidents:
        raw = inc.get("neighborhood")
        if not raw or raw == "-":
            continue
        display = display_name(city_slug, str(raw))
        if not display:
            continue
        slug = hood_slug(display)
        if not slug:
            continue
        g = groups.setdefault(display, {"slug": slug, "incidents": [], "count": 0, "raw": str(raw)})
        g["incidents"].append(inc)
        g["count"] += 1
    return groups
