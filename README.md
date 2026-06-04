# tidycop

**Python port of [tidycops](https://github.com/Steal-This-Code/tidycops)** —
city-agnostic interface for public police incident data.

## Status

**v0.3.0** — 25 U.S. cities live across Socrata / ArcGIS / CKAN.
Command-line interface (`tidycop fetch ...`). Optional sqlite-backed
dedup layer. SpotCrime 8-category classifier extracted to the
separate [`tidycop-spotcrime`](https://github.com/colinmac-boop/tidycop-spotcrime)
package (soft-imported when `--classify-spotcrime` is requested).
172 unit tests pass, 30 network-gated tests skipped by default.

The repo also ships **`web/`** — the static site for
[citycrimemap.us](https://citycrimemap.us), a worked example of
consuming `tidycop` + `tidycop-spotcrime` to render Leaflet maps for
5 cities. See [`web/README.md`](web/README.md) for the refresh /
redeploy flow.

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

## Supported Cities (v0.2.0 — 25 total)

| City | Provider(s) | Sources | Aliases |
|---|---|---|---|
| Boston | ArcGIS | 1 | — |
| Chicago | Socrata | 1 | — |
| Cincinnati | Socrata | 2 (legacy + current) | `cincy`, `cincinnati_oh` |
| Cleveland | ArcGIS | 2 (legacy + P1RMS) | `cleveland_oh` |
| Dallas | Socrata | 1 | — |
| Denver | ArcGIS | 1 (rolling 5y) | `denver_co` |
| Detroit | ArcGIS | 1 | `detroit_mi` |
| Fort Lauderdale | Socrata | 1 (historical capped) | `ft_lauderdale`, `fortlauderdale`, `fort_lauderdale_fl` |
| Gainesville | Socrata | 1 | `gainesville_fl` |
| Grand Rapids | ArcGIS | 1 | `grandrapids`, `grand_rapids_mi`, `gr` |
| Hartford | ArcGIS | 1 (rolling) | `hartford_ct` |
| Houston | ArcGIS | 4 NIBRS layers | `houston_tx`, `htx` |
| Indianapolis | ArcGIS | 1 | `indy`, `indianapolis_in` |
| Kansas City | Socrata | 12 per-year | `kansas_city_mo`, `kansascity`, `kc` |
| Minneapolis | ArcGIS | 1 (2yr rolling) | `mpls`, `minneapolis_mn` |
| Naperville | ArcGIS | 2 (legacy + NIBRS) | `naperville_il` |
| New Orleans | Socrata | 16 per-year (CFS) | `nola`, `new_orleans_la` |
| New York City | Socrata | 2 (historic + current) | `nyc`, `new_york_city` |
| Pittsburgh | CKAN (WPRDC) | 1 | `pgh`, `pittsburgh_pa` |
| Providence | Socrata | 1 (rolling 180d) | — |
| Rochester | ArcGIS | 1 (Part I only) | `rochester_ny` |
| San Antonio | CKAN | 1 | `sanantonio`, `sa`, `satx`, `san_antonio_tx` |
| San Francisco | Socrata | 1 | `sf` |
| Seattle | Socrata | 1 | — |
| Washington, DC | ArcGIS | 19 per-year MPD | `dc`, `washington`, `district_of_columbia` |

## Why This Exists

Public police data is fragmented:
- Different platforms (Socrata, ArcGIS, CKAN, custom)
- Different schemas (`primary_type` vs. `nibrs_offense_code_description`)
- Different timezones, date formats, coordinate systems
- Different coalesce-fallback patterns (Detroit's record-id is a 3-way
  fallback across `incident_entry_id`, `crime_id`, and `ESRI_OID`)

**tidycop** handles all of that. One call, one schema out.

## Command-Line Interface

```bash
# Fetch one week of Chicago incidents as CSV to stdout
tidycop fetch chicago --start 2026-04-01 --end 2026-04-07

# JSON output to a file
tidycop fetch sf --start 2026-04-01 --end 2026-04-07 \
    --output json --out-path /tmp/sf.json

# Parquet output (requires --out-path; pyarrow or fastparquet must be installed)
tidycop fetch nyc --start 2026-04-01 --end 2026-04-07 \
    --output parquet --out-path /tmp/nyc.parquet

# city_full view with the SpotCrime 8-category classifier
tidycop fetch detroit --start 2026-04-01 --end 2026-04-07 \
    --view city_full --classify-spotcrime

# List supported cities (optionally filter by provider)
tidycop cities
tidycop cities --provider arcgis
tidycop cities --json
```

## Deduplication (opt-in)

For incremental pulls — e.g. a daily producer that should only ship rows
it hasn't already shipped — pass a sqlite path:

```python
from pathlib import Path
import tidycop

db = Path("./state/seen.sqlite")
new = tidycop.get_incidents(
    "chicago",
    "2026-04-01",
    "2026-04-07",
    dedup_db=db,
)
# First call: every row. Second call with the same window: only newly
# published / edited rows. (city, source_id, content_hash) is the key;
# provenance columns are intentionally excluded from the hash so a row
# that migrates between source slices is not seen as a new record.
```

## SpotCrime category classifier (opt-in, extension package)

The SpotCrime product groups every incident into 8 buckets (Shooting,
Robbery, Assault, Burglary, Theft, Arson, Vandalism, Arrest). The
classifier lives in a separate package,
[`tidycop-spotcrime`](https://github.com/colinmac-boop/tidycop-spotcrime),
so `tidycop` stays city-agnostic. The 5 MVP cities ship per-source
mappings in `registry/cities.yaml` under `spotcrime_category_map`.

```bash
pip install tidycop-spotcrime
```

```python
df = tidycop.get_incidents(
    "chicago",
    "2026-04-01",
    "2026-04-07",
    classify_spotcrime=True,  # adds std_spotcrime_category column
)
df[["std_offense_category", "std_spotcrime_category"]].head()
```

Without `tidycop-spotcrime` installed, `classify_spotcrime=True` (and
`tidycop fetch --classify-spotcrime`) raises a clear `ImportError`
pointing at the install command. Unmapped natives stay null. Fatal
shootings collapse into `Shooting` (the separate `Homicide` bucket was
removed 2026-05-26).

## Installation

```bash
# When packaged for PyPI (not yet):
#   pip install tidycop

# For now, from source:
git clone https://github.com/colinmac-boop/tidycop
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
├── cli.py                # 'tidycop' entry point: fetch + cities subcommands
└── dedup.py              # sqlite-backed (city, source_id, content_hash)

# SpotCrime classifier lives in the separate tidycop-spotcrime package
# (see https://github.com/colinmac-boop/tidycop-spotcrime). It's an
# optional extension; tidycop soft-imports it when classify_spotcrime=True.

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

- **CityCrimeMap** (`web/` in this repo, live at
  [citycrimemap.us](https://citycrimemap.us)) — worked example of
  a static map site consuming the library.
- **SpotCrime / spotcops producer** — replace email ingest with
  tidycop + SFTP delivery.
- **HomeStoop** — pull local incidents for user's address, filter
  by radius.
- **CrimeGrade.org** — cross-city comparable data for grading.
- **Standalone library** — pip-installable for researchers,
  journalists, civic tech.

### Library / product boundary

`tidycop/` (the library) stays city-agnostic and in upstream parity
with the R `tidycops`. Cities not in upstream R
`incident_registry.R` belong in a downstream **overlay YAML** loaded
at call time:

```bash
tidycop fetch <city> --registry-path /path/to/your-overlay.yaml
```

or in Python:

```python
tidycop.get_incidents("yourcity", "2026-04-01", "2026-04-07",
                      registry_path="/path/to/your-overlay.yaml")
```

This lets downstream consumers (including `web/` if it ever needed
a non-upstream city) extend the registry without polluting the
library. The pre-commit guard at
`scripts/check_no_downstream_cities.py` enforces this on the
library half.

## Credits

Ported from [tidycops](https://github.com/Steal-This-Code/tidycops) (MIT,
Anthony Galvan). The 23-column std_* schema and the city → endpoint
crosswalks are direct ports of his work.

## License

MIT
