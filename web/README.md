# web/ — CityCrimeMap static site

The frontend that consumes `tidycop` and renders city crime maps.

- **Live:** https://citycrimemap.us (canonical)
- **Vercel preview:** https://citymaps.vercel.app
- **Vercel project:** `citymaps` (team `colinmac-1018`)
- **Cities:** Chicago, Seattle, San Francisco, Detroit, Pittsburgh
  (the 5 with populated `tidycop-spotcrime` classifier maps as of
  `tidycop` v0.3.0 / `tidycop-spotcrime` v0.1.0)
- **Old domain:** `neighborhoodcrimemap.com` — redirects to the canonical
  domain. We own it for squat-prevention.

## Refresh / redeploy

```bash
# 1. pull fresh data via the tidycop library
.venv/bin/python web/scripts/fetch_data.py

# 2. regenerate HTML (uses BASE_URL=https://citycrimemap.us by default)
.venv/bin/python web/scripts/generate_site.py

# 3. push to Vercel
cd web/pages && vercel --prod
```

To preview against the `citymaps.vercel.app` URL during development:

```bash
BASE_URL=https://citymaps.vercel.app .venv/bin/python web/scripts/generate_site.py
```

## Layout

```
web/
├── scripts/
│   ├── cities.py          # the 5 cities + windows + map centers + alerts URLs
│   ├── fetch_data.py      # tidycop → data/<slug>.json (+ _summary.json)
│   └── generate_site.py   # data → pages/<slug>.html + pages/index.html
├── data/                  # raw fetched JSON (committed for traceability)
└── pages/                 # static site root deployed to Vercel
    ├── index.html
    ├── chicago.html, seattle.html, san-francisco.html, detroit.html, pittsburgh.html
    ├── vercel.json
    └── data/<slug>.json   # regenerated at build time, gitignored
```

## City window tuning

Open-data portals lag the real world by days to weeks. Windows per
`scripts/cities.py`:

| City | Window | Why |
|---|---|---|
| Chicago | 45 days | Socrata `ijzp-q8t2` lags ~7-14 days |
| Seattle | 14 days | near-real-time |
| San Francisco | 14 days | near-real-time |
| Detroit | 14 days | near-real-time |
| Pittsburgh | 75 days | WPRDC lags ~45 days |

## Known limitations

- Seattle's `tidycop-spotcrime` classifier map keys on NIBRS categories
  (`BURGLARY/BREAKING&ENTERING`) but the dataset returns `PROPERTY
  CRIME`, so a chunk of Seattle rows still land in "Unclassified". Fix
  belongs in `tidycop-spotcrime` registry, not here.
- Tables cap at 1,500 incidents per city per fetch to keep
  `/data/<slug>.json` browser-friendly (largest is Chicago at ~176 KB).
- No incremental refresh — each fetch overwrites. Cron is not yet
  scheduled; refresh manually for now.

## Adding a 6th city

1. Confirm the city is in upstream `tidycops` (`registry/cities.yaml`
   here, or the upstream R `incident_registry.R`). If it's not in
   either, it doesn't go in the registry — see top-level `AGENTS.md`
   § Hard Boundary. Downstream cities go in a separate overlay YAML
   loaded via `--registry-path`.
2. If the city has no classifier map yet, add it to
   `tidycop-spotcrime` upstream. Don't paste a map into `tidycop`
   core.
3. Add the city dict to `scripts/cities.py`, then fetch / generate /
   deploy.
