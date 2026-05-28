# Changelog

All notable changes to **tidycop** are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning is [SemVer](https://semver.org/spec/v2.0.0.html).

## [0.2.0] — 2026-05-28

### Added

- **20 additional cities** ported from the upstream R registry, bringing
  the total to 25:
  - **Socrata:** dallas, cincinnati (legacy + current split), providence,
    gainesville, fort_lauderdale, kansas_city (12 per-year datasets),
    new_orleans (16 per-year calls-for-service), new_york (historic +
    current YTD).
  - **ArcGIS:** cleveland (legacy + P1RMS), rochester (Part I only),
    boston, hartford (rolling), indianapolis, denver, minneapolis
    (rolling 2yr), grand_rapids, naperville (legacy + NIBRS), houston
    (4 NIBRS group layers), washington_dc (19 per-year MPD layers).
  - **CKAN:** san_antonio (SAPD offenses).
- **Command-line interface** (`tidycop` entry point):
  - `tidycop fetch <city> --start YYYY-MM-DD --end YYYY-MM-DD`
  - `--output csv|json|parquet` with `--out-path` for file output.
  - `--view comparable|city_full|city_raw` mirroring the Python API.
  - `--limit N`, `--classify-spotcrime`.
  - `tidycop cities [--provider socrata|arcgis|ckan] [--json]`.
- **Deduplication layer** (`tidycop/dedup.py`):
  - `DedupStore`: sqlite-backed seen-set keyed on
    `(city, source_id, content_hash)` with WAL mode.
  - `content_hash(row)`: stable SHA-256 over `std_*` fields with
    provenance columns excluded (so a row migrating between source
    slices isn't double-counted).
  - `filter_new(df, ...)` convenience that records every hash and
    returns only the previously-unseen rows.
  - Opt-in via `get_incidents(..., dedup_db=Path(...))`.
- **SpotCrime 8-category classifier** (`tidycop/classifier.py`):
  - Categories: Shooting, Robbery, Assault, Burglary, Theft, Arson,
    Vandalism, Arrest. (Homicide bucket removed 2026-05-26; fatal
    shootings collapse into Shooting.)
  - Per-source mapping table at
    `SourceSpec.spotcrime_category_map` (loaded from
    `spotcrime_category_map:` blocks in `registry/cities.yaml`).
  - 5 MVP cities (chicago, seattle, san_francisco, detroit, pittsburgh)
    ship full mappings; remaining cities can be mapped as we port them.
  - Opt-in via `get_incidents(..., classify_spotcrime=True)` or
    `tidycop fetch ... --classify-spotcrime`.
- **Live smoke harness** (`tests/test_live_all_cities.py`): opt-in
  (`TIDYCOP_LIVE_ALL=1`) parametrized test that hits every registered
  city against a sane recent window and asserts shape (not row count;
  rolling/historical feeds may legitimately be empty).

### Changed

- `__version__` bumped to `0.2.0`.
- `SourceSpec` gains `spotcrime_category_map: dict[str, str]` (default
  empty).
- `test_list_supported_cities_shape` now asserts MVP-5 ⊆ registry
  rather than equality (registry has grown past MVP).
- `.gitignore` ignores OpenClaw workspace files (`AGENTS.md`,
  `SOUL.md`, `MEMORY.md`, `memory/`, `.openclaw/`, etc.).

### Notes / deferred

- **SFTP delivery mode** for the spotcops producer remains deferred
  (couples too tightly to spotcops internals; not in scope for tidycop
  proper).
- **Classifier coverage** for the 20 newly-ported cities is empty by
  default. The Python and CLI machinery is ready; the per-city
  mappings can land incrementally as the categories are reviewed.
- Some cities expose ambiguous offense categories (Recovered Vehicle,
  Other Offenses, Suspicious Occurrence). Those rows stay null in
  `std_spotcrime_category` rather than being force-mapped — downstream
  consumers can decide whether to drop, surface, or bucket them.

## [0.1.0] — 2026-05-27

Initial public port from the R `tidycops` package.

### Added

- 5 MVP cities: Chicago, Seattle, San Francisco, Detroit, Pittsburgh.
- Three platform fetchers: Socrata, ArcGIS, CKAN.
- 23-column `std_*` schema with coalesce-fallback field maps and
  timezone-aware date parsing.
- `tidycop.get_incidents()` end-to-end across all three providers, with
  `comparable` / `city_full` / `city_raw` view modes.
- 133 unit tests + per-provider opt-in live smoke tests.
