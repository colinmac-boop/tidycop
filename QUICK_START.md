# Quick Start — tidycop Development

## Location
`~/Projects/tidycop`

## Current Status
**Scaffolded, not functional yet.** All core files are stubs. Week 1 goal: working MVP with 5 cities.

## Reference Materials

### R Source (for porting)
```bash
cd /tmp/tidycops
# Key files:
# R/incident_registry.R      → registry/cities.yaml + tidycop/registry.py
# R/standardized_incidents.R → tidycop/schema.py
# R/data_utils.R             → tidycop/platform/*.py
# R/get_incidents.R          → tidycop/core.py
```

### Analysis Doc
`tidycop_analysis.md` in this repo — comprehensive overview, integration points, architecture

### TODO
`docs/TODO.md` — Day-by-day checklist for Week 1

### Porting Guide
`docs/PORTING_GUIDE.md` — R→Python translation patterns

## Development Setup

```bash
cd ~/Projects/tidycop

# Option 1: Poetry (recommended)
poetry install
poetry shell

# Option 2: pip
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest
pytest -v                    # verbose
pytest tests/test_core.py    # specific file
```

## First Task (Day 1)

Port Chicago's city spec from R to YAML:

1. Open `/tmp/tidycops/R/incident_registry.R`
2. Find the Chicago section (search for `chicago = "chicago"` in aliases)
3. Look for the source spec (provider="socrata", dataset_id, field_map)
4. Translate to `registry/cities.yaml`:

```yaml
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
```

Repeat for Seattle, SF, Detroit, Pittsburgh.

## Smoke Test Goal (End of Week)

```python
import tidycop

incidents = tidycop.get_incidents(
    city="chicago",
    start_date="2026-04-01",
    end_date="2026-04-30",
    view="comparable",
    limit=100
)

print(f"Fetched {len(incidents)} incidents")
print(incidents[['std_incident_date', 'std_offense_description', 'std_address']].head())
```

Should work by Day 5-6.

## Questions / Blockers?

Tag me in workspace or leave notes in `docs/NOTES.md`.
