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
- [ ] Wire `tidycop/core.py` → registry → fetcher → schema
- [ ] Implement `view="comparable"` mode
- [ ] Test: fetch Chicago incidents 2026-04-01 → 2026-04-30
- [ ] Validate: compare row count + schema vs. R tidycops

## Day 6: ArcGIS Fetcher
- [ ] Implement `tidycop/platform/arcgis.py`
- [ ] Feature layer query (where clause, outFields)
- [ ] resultOffset paging
- [ ] Test against Detroit (RMS Crime Incidents)

## Day 7: Polish + Docs
- [ ] Add type hints + docstrings
- [ ] Run black + ruff
- [ ] Write basic usage examples in README
- [ ] Tag v0.1.0

## Stretch Goals
- [ ] CKAN fetcher (Pittsburgh)
- [ ] `view="city_full"` mode
- [ ] CLI: `tidycop fetch chicago --start 2026-04-01`
- [ ] SpotCrime category classifier integration
