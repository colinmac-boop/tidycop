# TODO — Week 1 (2026-05-20 → 2026-05-27)

## Day 1-2: Registry + Schema
- [x] Port `incident_registry.R` city specs to `registry/cities.yaml` (2026-05-27)
- [x] Start with 5 MVP cities: Chicago, Seattle, SF, Detroit, Pittsburgh (2026-05-27)
- [x] Implement `tidycop/registry.py` (load YAML, normalize city keys) (2026-05-27)
- [x] Implement `tidycop/schema.py` (STD_COLUMNS, field coalescing) (2026-05-27)
  - 40 unit tests passing (registry: 23, schema: 16, core placeholder: 1)
  - Coalesce-fallback verified against Detroit's 3-way std_source_record_id
  - Date parsing: naive Socrata strings → city tz; ArcGIS epoch ms → city tz

## Day 3-4: Socrata Fetcher
- [x] Implement `tidycop/platform/socrata.py` (2026-05-27)
- [x] SoQL $where date filtering (end-exclusive day boundary) (2026-05-27)
- [x] Paging via $offset (PAGE_SIZE=1000, terminates on short page) (2026-05-27)
- [x] Rate limiting + retry (429/5xx, exponential backoff, Retry-After) (2026-05-27)
- [x] Test against Chicago (ijzp-q8t2) — live smoke + end-to-end normalize (2026-05-27)
  - 21 unit tests (mocked HTTP) + 3 live smoke tests (Chicago/Seattle/SF)
  - End-to-end fetch → normalize verified on all 3 Socrata cities, 2026-04-15

## Day 5: Core Integration
- [x] Wire `tidycop/core.py` → registry → fetcher → schema (2026-05-27)
- [x] Implement `view="comparable"` mode (also `city_full` and `city_raw`) (2026-05-27)
- [x] Test: fetch Chicago incidents live, 1-day window, all 3 views (2026-05-27)
- [ ] Validate: compare row count + schema vs. R tidycops (deferred — R install not needed for MVP; spot-check vs. native Chicago portal looks consistent)
  - Added `tidycop/platform/__init__.py` dispatch (`get_fetcher`, `register_fetcher`)
  - Added source selection via active_from/active_to overlap (currently no-op for MVP cities but ready for Cincinnati/Cleveland later)
  - 18 new tests in tests/test_core.py (FakeFetcher; no network)

## Day 6: ArcGIS Fetcher
- [x] Implement `tidycop/platform/arcgis.py` (2026-05-27)
- [x] Feature layer query (where clause, outFields, returnGeometry) (2026-05-27)
- [x] resultOffset + resultRecordCount paging (PAGE_SIZE 2000) (2026-05-27)
- [x] Test against Detroit RMS Crime Incidents — live + e2e via `tidycop.get_incidents('detroit', ...)` (2026-05-27)
  - 27 unit tests (HTTP mocked) + 1 live smoke test (opt-in)
  - End-to-end e2e: 500 rows for 1 week (2024-04-01..07), all 500 with lat/lon, coalesce-fallback on `std_source_record_id` working
  - Known gotcha: ArcGIS TIMESTAMP literals are interpreted in server tz (usually UTC), not city-local; documented in `_build_where` docstring

## Day 7: Polish + Docs
- [x] CKAN fetcher (Pittsburgh) — promoted from stretch, landed first (2026-05-27)
- [x] Run black + ruff (2026-05-27)
- [x] Write usage examples in README (2026-05-27)
- [x] Tag v0.1.0 (2026-05-27)
- [ ] More type hints + docstrings on internal helpers (deferred to v0.2)

## Stretch Goals (still open)
- [x] CKAN fetcher (Pittsburgh) — done Day 7
- [x] `view="city_full"` mode — done Day 5 (also `city_raw`)
- [x] CLI: `tidycop fetch chicago --start 2026-04-01` (v0.2.0 — csv/json/parquet, `tidycop cities`)
- [x] SpotCrime category classifier integration (v0.2.0 — 8-category, MVP-5 mapped)
- [x] Port remaining 20 cities from upstream R registry (v0.2.0 — 25 cities total)
- [x] Deduplication layer (v0.2.0 — `tidycop.dedup`, `get_incidents(..., dedup_db=...)`)
- [ ] SFTP delivery mode for spotcops producer (deferred to spotcops side; couples too tightly)

## v0.2.0 — Phase 2 (2026-05-28)
- [x] 5 Socrata cities ported: dallas, cincinnati, providence, gainesville, fort_lauderdale
- [x] 5 ArcGIS cities ported: cleveland, rochester, boston, hartford, indianapolis
- [x] 5 more cities ported: denver, minneapolis, grand_rapids, naperville, houston
- [x] Final 5 cities ported: washington_dc, kansas_city, new_orleans, san_antonio, new_york
- [x] CLI entry point + tests
- [x] sqlite dedup module + tests (18 unit + integration)
- [x] SpotCrime classifier + per-source mapping for 5 MVP cities (20 tests)
- [x] Per-city live smoke tests (parametrized, opt-in via `TIDYCOP_LIVE_ALL=1`)
- [x] Tag v0.2.0
