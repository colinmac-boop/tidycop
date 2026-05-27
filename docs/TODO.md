# TODO — Week 1 (2026-05-20 → 2026-05-27)

## Day 1-2: Registry + Schema
- [x] Port `incident_registry.R` city specs to `registry/cities.yaml` (2026-05-27)
- [x] Start with 5 MVP cities: Chicago, Seattle, SF, Detroit, Pittsburgh (2026-05-27)
- [ ] Implement `tidycop/registry.py` (load YAML, normalize city keys)
- [ ] Implement `tidycop/schema.py` (STD_COLUMNS, field coalescing)

## Day 3-4: Socrata Fetcher
- [ ] Implement `tidycop/platform/socrata.py`
- [ ] SoQL $where date filtering
- [ ] Paging (resultOffset or $offset)
- [ ] Rate limiting + retry (requests Session + backoff)
- [ ] Test against Chicago (ijzp-q8t2)

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
