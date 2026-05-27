"""City registry and spec loading.

Loads `registry/cities.yaml` and exposes lookup helpers. City keys are
normalized through an alias table declared inline in the YAML (each city
entry may include an `aliases: [...]` list).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# registry/cities.yaml lives at the repo root, one level above the package.
_PACKAGE_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PACKAGE_DIR.parent
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "registry" / "cities.yaml"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceSpec:
    """One data source for a city (a single Socrata/ArcGIS/CKAN endpoint)."""

    source_id: str
    display_name: str
    provider: str  # "socrata" | "arcgis" | "ckan" | "custom"
    dataset_id: str
    base_url: str
    date_field: str
    field_map: dict[str, str | list[str] | None]
    active_from: date | None = None
    active_to: date | None = None

    # Provider-specific extras (kept loose; fetchers consume what they need)
    extras: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CitySpec:
    """A city and its ordered list of data sources."""

    city: str  # canonical key, e.g. "chicago"
    display_name: str
    timezone: str  # IANA, e.g. "America/Chicago"
    sources: tuple[SourceSpec, ...]
    aliases: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------

# Fields that get pulled into SourceSpec proper; everything else lands in extras.
_SOURCE_CORE_FIELDS = {
    "source_id",
    "display_name",
    "provider",
    "dataset_id",
    "base_url",
    "date_field",
    "field_map",
    "active_from",
    "active_to",
}


def _coerce_date(value: Any) -> date | None:
    """Accept None, a date, a datetime, or an ISO date string."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Accept "YYYY-MM-DD" or full ISO; tolerate trailing T...Z.
        return datetime.fromisoformat(value.split("T")[0]).date()
    raise TypeError(f"Cannot coerce {value!r} to date")


def _build_source(raw: dict[str, Any]) -> SourceSpec:
    missing = [k for k in ("source_id", "provider", "base_url", "field_map") if k not in raw]
    if missing:
        raise ValueError(f"source missing required fields: {missing} in {raw!r}")

    extras = {k: v for k, v in raw.items() if k not in _SOURCE_CORE_FIELDS}

    return SourceSpec(
        source_id=raw["source_id"],
        display_name=raw.get("display_name", raw["source_id"]),
        provider=raw["provider"],
        dataset_id=raw.get("dataset_id", ""),
        base_url=raw["base_url"],
        date_field=raw.get("date_field", ""),
        field_map=dict(raw["field_map"]),
        active_from=_coerce_date(raw.get("active_from")),
        active_to=_coerce_date(raw.get("active_to")),
        extras=extras,
    )


def _build_city(key: str, raw: dict[str, Any]) -> CitySpec:
    if "sources" not in raw or not raw["sources"]:
        raise ValueError(f"city {key!r} has no sources")
    sources = tuple(_build_source(s) for s in raw["sources"])
    aliases = tuple(raw.get("aliases") or ())
    return CitySpec(
        city=key,
        display_name=raw.get("display_name", key.replace("_", " ").title()),
        timezone=raw.get("timezone", "UTC"),
        sources=sources,
        aliases=aliases,
    )


def load_registry(path: Path | str | None = None) -> dict[str, CitySpec]:
    """Load and parse the registry YAML.

    Returns a dict keyed by canonical city key.
    """
    p = Path(path) if path else DEFAULT_REGISTRY_PATH
    with p.open() as f:
        raw = yaml.safe_load(f) or {}
    cities_raw = raw.get("cities") or {}
    return {key: _build_city(key, spec) for key, spec in cities_raw.items()}


# ---------------------------------------------------------------------------
# Public API (cached lookups against the default registry)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _default_registry() -> dict[str, CitySpec]:
    return load_registry()


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """Map every alias (and canonical key) to its canonical city key."""
    index: dict[str, str] = {}
    for canonical, spec in _default_registry().items():
        index[canonical] = canonical
        for alias in spec.aliases:
            existing = index.get(alias)
            if existing and existing != canonical:
                raise ValueError(
                    f"alias collision: {alias!r} maps to both {existing!r} and {canonical!r}"
                )
            index[alias] = canonical
    return index


def normalize_city_key(city: str) -> str:
    """Resolve any alias/casing/whitespace to a canonical city key.

    Raises KeyError if the city is not recognized.
    """
    if not isinstance(city, str) or not city.strip():
        raise KeyError(f"invalid city key: {city!r}")
    key = city.strip().lower().replace("-", "_").replace(" ", "_")
    index = _alias_index()
    if key not in index:
        raise KeyError(f"unsupported city: {city!r}")
    return index[key]


def get_city_spec(city: str) -> CitySpec:
    """Return the CitySpec for the given city key or alias."""
    canonical = normalize_city_key(city)
    return _default_registry()[canonical]


def list_supported_cities() -> list[dict[str, Any]]:
    """Lightweight summary of every registered city (canonical key, display name, providers)."""
    out: list[dict[str, Any]] = []
    for key, spec in _default_registry().items():
        out.append(
            {
                "city": key,
                "display_name": spec.display_name,
                "timezone": spec.timezone,
                "aliases": list(spec.aliases),
                "providers": sorted({s.provider for s in spec.sources}),
                "source_count": len(spec.sources),
            }
        )
    return out


def _reset_cache() -> None:
    """Test helper: clear the cached registry so an updated YAML can be re-read."""
    _default_registry.cache_clear()
    _alias_index.cache_clear()
