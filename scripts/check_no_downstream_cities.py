#!/usr/bin/env python3
"""Boundary guard: catch downstream/product-specific city additions.

Run as a pre-commit hook or in CI. Exits non-zero if registry/cities.yaml
contains a city key that's flagged as downstream-only, or if the file's
header comments contain a known marker indicating it shouldn't be here.

Heuristic checks (cheap, no upstream R parse):

1. Hard deny-list of known downstream-only city keys. Update as needed.
2. Reject any spotcrime_category_map block whose enclosing city is NOT
   in the upstream-parity set (defined inline below as
   UPSTREAM_TIDYCOPS_CITIES, kept in sync with R `incident_registry.R`).
   Cities in the upstream set may keep `spotcrime_category_map` (it's an
   opt-in downstream annotation on a legitimate library city).
3. Reject magic markers like "SpotCrime data2" or "downstream feed" in
   city-block comments — usually a sign the entry was added for a
   product, not for upstream parity.

Exit codes:
    0 = clean
    1 = violation(s) found
    2 = script error (yaml parse, missing registry, etc.)
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("error: PyYAML required to run boundary check", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "registry" / "cities.yaml"


# Cities that exist in the upstream R tidycops registry as of v0.2.0.
# Keep this in sync with /tmp/tidycops_src/R/incident_registry.R. If the
# upstream library adds a city, mirror it here.
# Verified 2026-05-29 against /tmp/tidycops_src/R/incident_registry.R (25 cities).
# To refresh: `grep -E '^  [a-z_]+ = list\(' /tmp/tidycops_src/R/incident_registry.R`
UPSTREAM_TIDYCOPS_CITIES: set[str] = {
    # 5 MVP cities
    "chicago", "san_francisco", "pittsburgh", "detroit", "seattle",
    # Socrata batch
    "dallas", "cincinnati", "providence", "gainesville", "fort_lauderdale",
    # ArcGIS batch
    "cleveland", "rochester", "boston", "hartford", "indianapolis",
    "denver", "minneapolis", "grand_rapids", "naperville", "houston",
    # Heavy hitters
    "washington_dc", "kansas_city", "new_orleans", "san_antonio", "new_york",
}


# Hard deny-list: cities that exist downstream (e.g. SpotCrime overlay)
# but NOT in upstream R tidycops. Adding any of these to the core
# registry is a boundary violation.
DOWNSTREAM_ONLY_CITIES: set[str] = {
    "boise",
    "boise_id",
}


# Magic markers in comments that suggest a downstream-only addition.
DOWNSTREAM_MARKERS: tuple[str, ...] = (
    "spotcrime data2",
    "data2 daily feed",
    "data2 feed",
    "downstream feed",
    "spotcrime feed",
)


def main() -> int:
    if not REGISTRY_PATH.exists():
        print(f"error: registry not found at {REGISTRY_PATH}", file=sys.stderr)
        return 2

    raw_text = REGISTRY_PATH.read_text()
    try:
        raw = yaml.safe_load(raw_text) or {}
    except yaml.YAMLError as e:
        print(f"error: yaml parse failed: {e}", file=sys.stderr)
        return 2

    cities = (raw.get("cities") or {}) if isinstance(raw, dict) else {}
    violations: list[str] = []

    # Check 1: deny-list
    for key in cities:
        if key in DOWNSTREAM_ONLY_CITIES:
            violations.append(
                f"city {key!r} is on the downstream-only deny-list — "
                "move it to a downstream overlay (e.g. "
                "~/.openclaw/workspace/spotcrime_sources/cities.yaml)"
            )

    # Check 2: cities not in upstream set that ship a spotcrime_category_map
    # are suspicious (we allow upstream cities to ship one as opt-in).
    for key, spec in cities.items():
        if key in UPSTREAM_TIDYCOPS_CITIES:
            continue
        if not isinstance(spec, dict):
            continue
        for src in spec.get("sources") or []:
            if isinstance(src, dict) and src.get("spotcrime_category_map"):
                violations.append(
                    f"city {key!r} ships spotcrime_category_map but is "
                    "not in UPSTREAM_TIDYCOPS_CITIES — likely a downstream "
                    "addition. Update UPSTREAM_TIDYCOPS_CITIES if upstream "
                    "added it, or move the entry to a downstream overlay."
                )

    # Check 3: downstream markers in raw text
    lowered = raw_text.lower()
    for marker in DOWNSTREAM_MARKERS:
        if marker in lowered:
            violations.append(
                f"registry/cities.yaml contains the marker {marker!r}; "
                "this suggests a downstream-only addition. Remove or "
                "rephrase the comment, and move the city if it's not in "
                "upstream R tidycops."
            )

    if violations:
        print("tidycop boundary check FAILED:", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print(
            "\nSee AGENTS.md → 'Hard Boundary' for the rule.",
            file=sys.stderr,
        )
        return 1

    print(f"tidycop boundary check passed ({len(cities)} cities, all upstream).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
