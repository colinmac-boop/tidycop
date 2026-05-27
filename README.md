# tidycop

**Python port of [tidycops](https://github.com/Steal-This-Code/tidycops)** —
city-agnostic interface for public police incident data.

## Status

**v0.1.0 (MVP)** — Working end-to-end across 5 U.S. cities (Chicago, Seattle,
San Francisco, Detroit, Pittsburgh). Three platform fetchers (Socrata,
ArcGIS, CKAN). 23-column standardized schema with timezone-aware date
parsing and coalesce-fallback field mapping. 133 unit tests, all passing.

## What It Does

One API to pull and normalize police incident data across U.S. cities that
publish through Socrata, ArcGIS, or CKAN open-data portals:

```python
import tidycop

# Comparable view (default) — only the 23 std_* columns. Best for
# cross-city analysis.
df = tidycop.get_incidents(
    city="chicago",
    start_date="2026-04-01",
    end_date="2026-04-30",
    limit=1000,
)
# df.columns == ['std_city', 'std_city_display', 'std_source_id', ...,
#                'std_incident_date', 'std_offense_description', ...,
#                'std_latitude', 'std_longitude']

# Aliases work too.
df = tidycop.get_incidents("sf", "2026-04-01", "2026-04-30")
df = tidycop.get_incidents("pgh", "2026-04-01", "2026-04-30")
df = tidycop.get_incidents("detroit_mi", "2026-04-01", "2026-04-30")
```

### Three views

```python
# Comparable: 23 std_* columns only (default)
df = tidycop.get_incidents("chicago", "2026-04-15", "2026-04-15")

# city_full: raw native columns + std_* columns side-by-side
df = tidycop.get_incidents(
    "chicago", "2026-04-15", "2026-04-15", view="city_full"
)

# city_raw: untouched source payload, no std_* columns
df = tidycop.get_incidents(
    "chicago", "2026-04-15", "2026-04-15", view="city_raw"
)
```

### Discovery

```python
import tidycop

# All wired cities with provider + alias info
for c in tidycop.list_supported_cities():
    print(c["city"], c["aliases"], c["providers"])
# chicago [] ['socrata']
# seattle [] ['socrata']
# san_francisco ['sf'] ['socrata']
# detroit ['detroit_mi'] ['arcgis']
# pittsburgh ['pgh', 'pittsburgh_pa'] ['ckan']

# Full city spec (timezone, source endpoints, field_map)
spec = tidycop.get_city_spec("sf")
print(spec.timezone, spec.sources[0].dataset_id)
# America/Los_Angeles wg3w-h783

# Canonical key from any alias
tidycop.normalize_city_key("PGH")  # → 'pittsburgh'

# The 23-column schema constant
tidycop.STD_COLUMNS
```

## Supported Cities (MVP — v0.1.0)

| City | Provider | Dataset | Timezone | Aliases |
|---|---|---|---|---|
| Chicago | Socrata | `ijzp-q8t2` | America/Chicago | — |
| Seattle | Socrata | `tazs-3rd5` | America/Los_Angeles | — |
| San Francisco | Socrata | `wg3w-h783` | America/Los_Angeles | `sf` |
| Detroit | ArcGIS | `8e532daee…` | America/New_York | `detroit_mi` |
| Pittsburgh | CKAN (WPRDC) | `bd41992a-…` | America/New_York | `pgh`, `pittsburgh_pa` |

More cities live in `registry/cities.yaml` once the upstream R registry is
fully ported (Phase 2).

## Why This Exists

Public police data is fragmented:
- Different platforms (Socrata, ArcGIS, CKAN, custom)
- Different schemas (`primary_type` vs. `nibrs_offense_code_description`)
- Different timezones, date formats, coordinate systems
- Different coalesce-fallback patterns (Detroit's record-id is a 3-way
  fallback across `incident_entry_id`, `crime_id`, and `ESRI_OID`)

**tidycop** handles all of that. One call, one schema out.

## Installation

```bash
# When packaged for PyPI (not yet):
#   pip install tidycop

# For now, from source:
git clone https://github.com/<org>/tidycop
cd tidycop
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Development

```bash
# Unit tests (no network)
pytest

# With live API smoke tests against the real city portals
TIDYCOP_LIVE_SOCRATA=1 \
TIDYCOP_LIVE_ARCGIS=1 \
TIDYCOP_LIVE_CKAN=1 \
  pytest

# Lint + format
ruff check tidycop tests
black tidycop tests
```

### Optional environment variables

| Variable | Purpose |
|---|---|
| `SOCRATA_APP_TOKEN` | Increases Socrata anonymous rate limits. Optional. |
| `ARCGIS_TOKEN` | For authenticated ArcGIS feature layers. Most public layers don't need it. |
| `CKAN_API_KEY` | For protected CKAN resources. Most public datasets don't need it. |

## Architecture

```
tidycop/
├── __init__.py           # Top-level: get_incidents, list_supported_cities,
│                         #   get_city_spec, normalize_city_key, STD_COLUMNS
├── core.py               # get_incidents() — registry → fetcher → schema
├── registry.py           # YAML loader, CitySpec / SourceSpec dataclasses,
│                         #   alias resolution
├── schema.py             # STD_COLUMNS (23), normalize() with coalesce
│                         #   fallback + timezone-aware date parsing
└── platform/
    ├── __init__.py       # Provider → fetcher dispatch
    ├── base.py           # BaseFetcher abstract class
    ├── socrata.py        # SoQL $where + $offset paging, retry, app token
    ├── arcgis.py         # ArcGIS REST query, resultOffset paging, error
    │                     #   envelope handling, geometry promotion
    └── ckan.py           # datastore_search_sql, SQL identifier escaping

registry/
└── cities.yaml           # Source-of-truth city → endpoint config
```

## Design Notes

- **Coalesce-fallback in field_map.** A field_map value can be a string (one
  source field) or a list of strings (try each in order, first non-null
  wins). Used by Detroit, Pittsburgh, Cincinnati, Cleveland, etc.
- **Timezone-aware dates.** All `std_incident_date` / `std_reported_date`
  values come out as tz-aware `pandas.Timestamp` in the city's local
  timezone. Socrata naive strings, ISO-with-offset strings, ArcGIS epoch
  milliseconds, and Python `datetime` objects all flow through one
  `_parse_dt` helper.
- **End-exclusive day boundaries.** `start_date` and `end_date` are both
  inclusive at the API level; under the hood the WHERE clause uses
  `< (end+1)` so a full day of records on `end_date` is always included.
- **Provider-specific gotcha (ArcGIS):** TIMESTAMP literals are interpreted
  in the server's timezone (usually UTC), not city-local. For day-level
  analytics this is fine; if exact city-local cutoffs matter, post-filter
  on `std_incident_date`.

## Integration Targets

- **SpotCrime / spotcops producer** — replace email ingest with tidycop +
  SFTP delivery
- **HomeStoop** — pull local incidents for user's address, filter by radius
- **CrimeGrade.org** — cross-city comparable data for grading
- **Standalone library** — pip-installable for researchers, journalists,
  civic tech

## Credits

Ported from [tidycops](https://github.com/Steal-This-Code/tidycops) (MIT,
Anthony Galvan). The 23-column std_* schema and the city → endpoint
crosswalks are direct ports of his work.

## License

MIT
