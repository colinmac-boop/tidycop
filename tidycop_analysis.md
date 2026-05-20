# tidycops Analysis & Python Port Plan

**Date:** 2026-05-20  
**Source:** https://github.com/Steal-This-Code/tidycops (MIT license, Anthony Galvan)  
**Context:** Colin wants to integrate this across multiple projects (SpotCrime, HomeStoop, CrimeGrade, AustinCrimeMap) and possibly make it standalone.

---

## What tidycops Is

An R package providing **city-agnostic wrappers** for pulling + normalizing public police incident data from 25+ U.S. cities. Think of it as a `tidyverse`-style interface to the fragmented landscape of city open-data portals.

### Key features
1. **Unified API** — one `get_incidents(city, start_date, end_date)` call works across Chicago, Seattle, NYC, etc.
2. **Standardized schema** — 23 `std_*` columns (incident_id, incident_date, offense_description, address, lat/lon, beat, district, etc.) mapped from heterogeneous source fields
3. **Multiple output modes:**
   - `view="comparable"` — only standardized fields (cross-city analysis)
   - `view="city_full"` — all native fields + `std_*` columns
   - `view="city_raw"` — untouched source payload
4. **Multi-platform support:**
   - **Socrata** (Chicago, Cincinnati, Seattle, KC, Hartford, Gainesville, etc.)
   - **ArcGIS** (Detroit, Denver, Grand Rapids, Minneapolis, Houston, Boston, etc.)
   - **CKAN** (Pittsburgh, San Antonio)
   - **Custom** (Dallas legacy, NYCOpenData, etc.)
5. **MIT license** — we can port freely

### Cities currently wired (25+)
Boston, Chicago, Cincinnati, Cleveland, Dallas, Denver, Detroit, Fort Lauderdale, Gainesville, Grand Rapids, Hartford, Houston, Indianapolis, Kansas City, Minneapolis, Naperville, New Orleans, NYC, Pittsburgh, Providence, Rochester, San Antonio, San Francisco, Seattle, Washington DC

### What it doesn't cover (yet)
- Arrests (only incidents)
- Use-of-force
- Officer-involved shootings (stub functions exist but minimal coverage)
- Real-time feeds (most are rolling windows: 2yr, 5yr, or YTD + current year)
- Baltimore, LA, Austin (matrix shows them as "hard" or custom — not yet wired)

---

## Architecture Overview

```
┌────────────────────┐
│  USER CODE         │  get_incidents(city="chicago", start_date="2026-04-01", view="comparable")
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  ADAPTER LAYER     │  normalize_incident_city_key("chicago") → "chicago"
│  (incident_        │  get_incident_city_spec("chicago") → {provider: "socrata", dataset_id: "ijzp-q8t2", field_map: {...}}
│   registry.R)      │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  PLATFORM FETCHER  │  fetch_socrata(), fetch_arcgis(), fetch_ckan()
│  (data_utils.R)    │  → raw JSON/CSV from city API
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  NORMALIZATION     │  Map raw fields → std_* schema via field_map
│  (standardized_    │  Parse dates with city timezone, coalesce fallback fields
│   incidents.R)     │  Normalize text (lowercase offense descriptions, etc.)
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  OPTIONAL CLEANUP  │  Dedupe by source_record_id, filter by offense/beat/zip, convert to sf
│  (clean_data.R)    │
└────────┬───────────┘
         │
         ▼
     RETURN tibble or sf
```

**Key files:**
- `R/incident_registry.R` — city-to-endpoint mappings + field crosswalks (the most valuable artifact for porting)
- `R/standardized_incidents.R` — schema definition + normalization logic
- `R/get_incidents.R` — main entry point
- `R/data_utils.R` — platform fetchers (Socrata/ArcGIS/CKAN HTTP wrappers)
- `city_incident_platform_matrix.md` — spreadsheet of all 50+ cities, which are wired vs. "hard" to integrate

---

## Why This Matters for SpotCrime / HomeStoop / etc.

### Current state
- We ingest crime data via **email forwards** (`data2@spotcrime.com`) and manual scraping (Baltimore County news/blotter, Jonesboro, shooting-news-scan)
- Each city is ad-hoc: different CSV formats, fragile parsers, zero cross-city consistency
- `spotcops/SPEC.md` in this workspace already sketched a **Python port + SFTP delivery** plan (May 15) to replace the email pipeline

### What tidycops gives us
1. **25 cities already mapped** — endpoints, field crosswalks, timezone handling, platform quirks. We don't have to reverse-engineer Socrata $where syntax or ArcGIS feature-layer paging for the 15th time.
2. **Standardized schema** — the `std_*` columns are a mature, tested crosswalk. We can adopt them wholesale (or extend them for SpotCrime's 9-category taxonomy).
3. **MIT license** — we can fork, port to Python, modify the schema, productionize it, and even release our own version as a standalone library if we want community adoption.
4. **Competitive intel** — see how someone else solved the same "normalize 25 city schemas" problem. Their offense-category groupings, their handling of redacted addresses, their date-parsing edge cases — all visible in the R code.

---

## Python Port Plan — `tidycop` (singular)

### Name
**`tidycop`** (singular) — Python package, pip-installable, MIT license.

### Scope (MVP)
1. Port the **incident registry** (city/endpoint/field mappings) to YAML or JSON
2. Implement **platform fetchers** (Socrata, ArcGIS, CKAN) as Python classes with paging, rate-limiting, retry
3. Implement the **standardized schema** (`std_*` columns) and normalization logic
4. Main API: `tidycop.get_incidents(city="chicago", start_date="2026-04-01", view="comparable")`
5. Optional: extend schema to support SpotCrime's 9-category taxonomy (`std_spotcrime_category` = Arrest/Arson/Assault/Burglary/...)

### Scope (Phase 2)
6. Arrests, UOF, OIS adapters (where available)
7. SFTP delivery mode for `spotcops` producer (ties into `spotcops/SPEC.md`)
8. Deduplication layer (sqlite state, track seen `(city, source_id, content_hash)`)
9. CLI tool: `tidycop fetch chicago --start 2026-04-01 --end 2026-04-30 --output csv`

### Architecture (Python)

```python
# registry/cities.yaml
cities:
  chicago:
    display_name: "Chicago"
    timezone: "America/Chicago"
    sources:
      - source_id: "chicago-pd-socrata"
        provider: "socrata"
        dataset_id: "ijzp-q8t2"
        base_url: "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
        date_field: "date"
        field_map:
          std_incident_id: "id"
          std_incident_number: "case_number"
          std_incident_date: "date"
          std_offense_code: "iucr"
          std_offense_description: "primary_type"
          std_address: "block"
          std_beat: "beat"
          std_district: "district"
          std_latitude: "latitude"
          std_longitude: "longitude"

# tidycop/__init__.py
from tidycop.core import get_incidents
from tidycop.registry import list_supported_cities
__version__ = "0.1.0"

# tidycop/core.py
def get_incidents(
    city: str,
    start_date: str | date,
    end_date: str | date,
    view: Literal["comparable", "city_full", "city_raw"] = "comparable",
    limit: int = 1000,
    as_gdf: bool = False,  # return geopandas GeoDataFrame if True
) -> pd.DataFrame | gpd.GeoDataFrame:
    """Fetch incidents for a supported city."""
    spec = registry.get_city_spec(city)
    fetcher = platform.get_fetcher(spec.provider)  # SocrataFetcher, ArcGISFetcher, etc.
    raw = fetcher.fetch(spec, start_date, end_date, limit)
    normalized = normalize(raw, spec.field_map, spec.timezone)
    if view == "comparable":
        return normalized[STD_COLUMNS]
    elif view == "city_full":
        return pd.concat([raw, normalized], axis=1)
    else:
        return raw

# tidycop/platform/socrata.py
class SocrataFetcher:
    def fetch(self, spec, start_date, end_date, limit):
        # Implement Socrata $where, $limit, paging, retry
        pass

# tidycop/platform/arcgis.py
class ArcGISFetcher:
    def fetch(self, spec, start_date, end_date, limit):
        # Implement ArcGIS REST query, outFields, resultOffset paging
        pass
```

### Directory structure
```
tidycop/
├── pyproject.toml          # Poetry or setuptools, MIT license
├── README.md
├── tidycop/
│   ├── __init__.py
│   ├── core.py             # get_incidents(), get_arrests(), etc.
│   ├── registry.py         # city_spec loading, normalization
│   ├── schema.py           # STD_COLUMNS, normalize(), parse_datetime()
│   ├── platform/
│   │   ├── socrata.py
│   │   ├── arcgis.py
│   │   ├── ckan.py
│   │   └── base.py         # BaseFetcher abstract class
│   └── cli.py              # optional CLI (typer or click)
├── registry/
│   ├── cities.yaml         # ported from incident_registry.R
│   └── platform_matrix.yaml  # ported from city_incident_platform_matrix.md
└── tests/
    ├── test_core.py
    ├── test_socrata.py
    └── test_arcgis.py
```

---

## Integration Points

### 1. **SpotCrime (spotcops producer)**
- Replace the email ingest with `tidycop` as the data source
- Run cron jobs per city (OpenClaw cron or system cron)
- Fetch incidents via `tidycop.get_incidents(city, last_n_days=1)`
- Classify into SpotCrime's 9 categories (`scripts/classify/rules.py`)
- Dedupe against `state/seen.sqlite`
- Deliver via SFTP to `/incoming/spotcops/v2/...` (per `spotcops/SPEC.md`)
- **Benefit:** 25 cities wired instantly, zero scraping, no email parsing, standardized schema

### 2. **HomeStoop**
- Pull **local** incident data for a user's address/neighborhood
- Use `tidycop.get_incidents(city, start_date, end_date, view="comparable", as_gdf=True)`
- Filter by radius around user's lat/lon (geopandas spatial join)
- Display on map, send alerts when new incidents match user's watch zone
- **Benefit:** Turn HomeStoop into a city-agnostic "crime near me" app with 25 cities on day one

### 3. **CrimeGrade.org (research/analytics)**
- Pull cross-city comparable data for academic research, policy analysis, grading
- Use `view="comparable"` to get consistent `std_*` columns across all cities
- Example: "Compare robbery rates per capita across 25 cities, Q1 2026"
- **Benefit:** No more ad-hoc CSV wrangling per city; one API, one schema

### 4. **AustinCrimeMap**
- Austin isn't wired in tidycops yet (matrix shows "hard"), but we can add the adapter ourselves
- Once wired: same benefits as SpotCrime (standardized ingest, no scraping)
- Could also pull **other Texas cities** if we wire them (Dallas is already done, San Antonio is wired)

### 5. **Standalone library (public release)**
- Package `tidycop` as a standalone pip-installable library
- Open-source it (MIT) on GitHub (Steal-This-Code org? or our own?)
- Market it to:
  - Academic researchers (criminology, urban studies)
  - Civic tech / Code for America brigades
  - Other crime-mapping startups
  - Journalists covering public safety
- **Benefit:** Brand visibility, community contributions (more cities wired by others), recruiting pipeline

---

## Open Questions / Decisions

1. **Name:** `tidycop` (singular) or `tidycops` (plural)? I lean toward singular for the Python port to differentiate from the R package.

2. **Repo ownership:** Fork under `Steal-This-Code` org (collaborate with Anthony Galvan) or start fresh under `spotcrime` org?

3. **SpotCrime schema extension:** Do we map tidycops `std_offense_category` → SpotCrime's 9 categories, or add a new `std_spotcrime_category` field? The latter keeps the original taxonomy intact for non-SpotCrime users.

4. **SFTP delivery:** Is this `tidycop`'s responsibility, or a separate `spotcops` producer that _uses_ tidycop? (I lean toward the latter — keep tidycop generic, spotcops SpotCrime-specific.)

5. **Backfill:** When we first wire a city, how far back do we pull? Most feeds are rolling (2yr, 5yr), so "all available" varies.

6. **Baltimore:** tidycops doesn't have Baltimore wired (matrix shows it as "Custom/Other, easy"), but we already scrape Baltimore County news/blotter. Should we wire Baltimore City (Socrata) into tidycop, or keep the BCO scrapers as-is?

7. **Standalone release timeline:** MVP Python port first (internal), or go straight to public release?

---

## Rough Effort Estimate

| Phase | Task | Effort | Notes |
|---|---|---|---|
| 0 | Study tidycops R code + incident_registry.R | 1 day | Already mostly done (this doc) |
| 1 | Port incident_registry.R → `registry/cities.yaml` | 2 days | Manual transcription, 25 cities |
| 2 | Implement Socrata fetcher + schema normalization | 3 days | Paging, $where syntax, retry, rate-limit |
| 3 | Implement ArcGIS fetcher | 2 days | Feature layer query, resultOffset paging |
| 4 | Implement CKAN fetcher | 1 day | Simpler than Socrata/ArcGIS |
| 5 | Wire SpotCrime 9-category classifier | 1 day | Extend schema with `std_spotcrime_category` |
| 6 | Test against 5 diverse cities (Chicago, Seattle, Detroit, Pittsburgh, SF) | 2 days | Smoke tests, schema validation |
| 7 | Integrate into spotcops producer (cron, dedup, SFTP) | 3 days | Per `spotcops/SPEC.md` |
| 8 | Package as pip-installable library (`pyproject.toml`, README, docs) | 2 days | |
| **Total (MVP)** | | **~17 days** | One developer, full-time |

Phase 2 (arrests, UOF, CLI, public release): +1-2 weeks.

---

## Next Steps

1. **Colin decision:** Do we want this as:
   - (a) Internal library only (for spotcops producer)?
   - (b) Internal + standalone public release?
   - (c) Contribution back to Anthony Galvan's tidycops repo (R + Python in same repo)?

2. **Priority cities:** Which 5-10 cities do we wire first? Recommend: Chicago, Seattle, Detroit, San Francisco, Pittsburgh (covers Socrata, ArcGIS, CKAN).

3. **Repo setup:** Create `tidycop` repo (GitHub, private or public?), scaffold Python package structure.

4. **Parallel work:** Can spotcops SFTP receiver be built in parallel while tidycop is being ported? (Yes — we already have `spotcops/SPEC.md` defining the wire format.)

5. **Baltimore question:** Do we wire Baltimore City (Socrata) into tidycop, or keep BCO scrapers separate?

---

## Related Files in Workspace
- `spotcops/SPEC.md` — May 15 draft of SFTP delivery pipeline (tidycop would feed into this)
- `memory/2026-05-15.md` — Colin's original "investigate tidycops" request, my initial recon
- `memory/data2_rules.md` — SpotCrime's 9-category taxonomy (Arrest, Arson, Assault, Burglary, Robbery, Shooting, Theft, Vandalism, Homicide)
- `scripts/validate_shooting_csv.py` — current CSV validator (would still be used post-tidycop, but the _input_ would be tidycop-generated CSVs)
