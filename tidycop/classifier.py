"""SpotCrime 8-category classifier.

The downstream SpotCrime product groups every incident into one of eight
buckets so it can be drawn on a map alongside the same eight buckets from
other cities. The classification lives outside the city registry's
"comparable" std_offense_category because:

  * The std_* schema is a faithful pass-through of native categories
    (e.g. Chicago's IUCR primary_type, Seattle's NIBRS offense_category).
    It's deliberately heterogeneous.
  * SpotCrime categories are a *product* taxonomy, not a city-portal
    one. Wiring them in as a separate column lets analysts keep both.

Categories (8, current as of 2026-05-26):

    Shooting    — discharge of a firearm, with or without victim. Fatal
                  shootings (formerly "Homicide") now collapse here.
    Robbery     — taking by force or threat of force.
    Assault     — non-robbery violence: aggravated/simple/threats.
    Burglary    — forced or unlawful entry to a structure.
    Theft       — larceny without entry: pickpocket, shoplift, motor
                  vehicle theft, theft from vehicle.
    Arson       — intentional fire-setting.
    Vandalism   — criminal damage / mischief / graffiti.
    Arrest     — non-incident: an arrest report rather than a crime
                  report. Some feeds (Chicago) don't emit these at all;
                  others (NYC complaint feed) interleave them.

Anything that doesn't map cleanly stays as ``None`` in
``std_spotcrime_category``. That's a feature: downstream consumers can
either drop those rows, surface them for human review, or fold them into
an "Other" bucket of their own.

Per-city mapping lives in ``registry/cities.yaml`` as
``spotcrime_category_map: {NATIVE: SPOTCRIME}`` under each source. The
mapping key is matched **case-insensitively** against
``std_offense_category`` first and ``std_offense_description`` second
(some feeds put the recognizable bucket name in the description column).
"""

from __future__ import annotations

import logging
from typing import Any, Mapping

import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

SPOTCRIME_CATEGORIES: tuple[str, ...] = (
    "Shooting",
    "Robbery",
    "Assault",
    "Burglary",
    "Theft",
    "Arson",
    "Vandalism",
    "Arrest",
)

SPOTCRIME_CATEGORY_SET: set[str] = set(SPOTCRIME_CATEGORIES)


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


def _normalize_key(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    s = str(value).strip().upper()
    return s or None


def classify_row(
    row: Mapping[str, Any] | pd.Series,
    mapping: Mapping[str, str],
) -> str | None:
    """Look up the SpotCrime category for one normalized row.

    Strategy (matches the R upstream's order of operations):
        1. Look up ``std_offense_category`` (upper-cased) in ``mapping``.
        2. Fall back to ``std_offense_description``.
        3. Return ``None`` if nothing matches — caller decides how to
           surface that (drop, "Other" bucket, alert).

    The mapping keys are uppercased once at load time; values are passed
    through unchanged (and must be one of SPOTCRIME_CATEGORIES, validated
    by ``classify_frame``).
    """
    cat = _normalize_key(row.get("std_offense_category"))
    if cat is not None and cat in mapping:
        return mapping[cat]
    desc = _normalize_key(row.get("std_offense_description"))
    if desc is not None and desc in mapping:
        return mapping[desc]
    return None


def classify_frame(df: pd.DataFrame, mapping: Mapping[str, str] | None) -> pd.DataFrame:
    """Add a ``std_spotcrime_category`` column to ``df`` using ``mapping``.

    If ``mapping`` is None or empty, the column is added but left null
    (so downstream consumers can rely on the column existing).
    """
    out = df.copy()
    if not mapping:
        out["std_spotcrime_category"] = None
        return out

    # Validate values up front; cheaper than per-row, and gives a
    # readable error before we silently corrupt downstream analytics.
    bad = sorted({v for v in mapping.values() if v not in SPOTCRIME_CATEGORY_SET})
    if bad:
        raise ValueError(
            f"spotcrime_category_map has invalid target categories {bad!r}; "
            f"valid options: {SPOTCRIME_CATEGORIES}"
        )

    norm = {k.upper(): v for k, v in mapping.items()}

    cats = out.get("std_offense_category")
    descs = out.get("std_offense_description")

    def _lookup(idx: int) -> str | None:
        if cats is not None:
            k = _normalize_key(cats.iat[idx])
            if k is not None and k in norm:
                return norm[k]
        if descs is not None:
            k = _normalize_key(descs.iat[idx])
            if k is not None and k in norm:
                return norm[k]
        return None

    out["std_spotcrime_category"] = [_lookup(i) for i in range(len(out))]
    return out
