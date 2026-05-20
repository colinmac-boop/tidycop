# tidycop

**Python port of [tidycops](https://github.com/Steal-This-Code/tidycops)** — city-agnostic interface for public police incident data.

## Status

🚧 **In Development** — Initial port from R package. Target: production-ready within 1 week (2026-05-20).

## What It Does

One API to pull + normalize police incident data across 25+ U.S. cities:

```python
import tidycop

# Fetch incidents for Chicago, last 30 days
incidents = tidycop.get_incidents(
    city="chicago",
    start_date="2026-04-20",
    end_date="2026-05-20",
    view="comparable",  # standardized schema
    limit=1000
)

# Returns pandas DataFrame with std_* columns:
# std_incident_id, std_incident_date, std_offense_description,
# std_address, std_latitude, std_longitude, std_beat, std_district, etc.
```

### Supported Cities (MVP)

- Chicago (Socrata)
- Seattle (Socrata)
- San Francisco (Socrata)
- Detroit (ArcGIS)
- Pittsburgh (CKAN)

Full list (25+ cities): see `registry/cities.yaml`

### Why This Exists

Public police data is fragmented across:
- Different platforms (Socrata, ArcGIS, CKAN, custom)
- Different schemas (Chicago's "primary_type" vs. Seattle's "offense_parent_group")
- Different timezones, date formats, coordinate systems

**tidycop** handles all of that. One interface, standardized output.

## Installation (when released)

```bash
pip install tidycop
```

## Development Setup

```bash
# Clone
git clone <repo-url>
cd tidycop

# Install dependencies
poetry install  # or: pip install -e ".[dev]"

# Run tests
pytest
```

## Architecture

```
tidycop/
├── __init__.py           # Main API: get_incidents()
├── core.py               # Core fetching logic
├── registry.py           # City spec loading
├── schema.py             # Standardized schema + normalization
└── platform/
    ├── socrata.py        # Socrata API wrapper
    ├── arcgis.py         # ArcGIS REST wrapper
    └── ckan.py           # CKAN datastore wrapper

registry/
├── cities.yaml           # City endpoint configs
└── platform_matrix.yaml  # Coverage matrix
```

## Integration

### SpotCrime (spotcops producer)
Replace email ingest with tidycop → SFTP delivery

### HomeStoop
Pull local incidents for user's address, filter by radius

### CrimeGrade.org
Cross-city comparable data for research/grading

### Standalone
pip-installable library for researchers, journalists, civic tech

## Credits

Ported from [tidycops](https://github.com/Steal-This-Code/tidycops) (MIT, Anthony Galvan).

## License

MIT
