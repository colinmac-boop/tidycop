# web/ — CityCrimeMap static site

The frontend that consumes `tidycop` and renders city crime maps.

- **Live:** https://citycrimemap.us (canonical)
- **Vercel preview:** https://citymaps.vercel.app
- **Vercel project:** `citymaps` (team `colinmac-1018`)
- **Cities (16 live):** Chicago, Seattle, San Francisco, Detroit,
  Pittsburgh, Washington DC, Houston, Rochester, Cleveland,
  Indianapolis, Hartford, Minneapolis, Cincinnati, Gainesville,
  Denver, Boston. See `docs/citymap-rollout-plan.md` for the
  remaining 9 and their blockers.
- **Old domain:** `neighborhoodcrimemap.com` — redirects to the canonical
  domain. We own it for squat-prevention.

## Refresh / redeploy

```bash
# 1. pull fresh data via the tidycop library
.venv/bin/python web/scripts/fetch_data.py

# 2. (optional) train hot spot models and emit risk-grid GeoJSON
#    Only cities present in HOTSPOT_CONFIG (predict_hotspots.py)
#    get a hotspots file; other cities are unaffected.
.venv/bin/python web/scripts/predict_hotspots.py

# 3. regenerate HTML (uses BASE_URL=https://citycrimemap.us by default)
.venv/bin/python web/scripts/generate_site.py

# 4. push to Vercel
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
│   ├── cities.py             # cities + windows + map centers + alerts URLs
│   ├── fetch_data.py         # tidycop → data/<slug>.json (+ _summary.json)
│   ├── predict_hotspots.py   # tidycop-hotspots → data/<slug>_hotspots.geojson
│   └── generate_site.py      # data → pages/<slug>.html + pages/index.html
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

## Predicted risk overlay (tidycop-hotspots)

As of 2026-07-03, Chicago's page has a toggleable **Predicted risk**
layer built with [tidycop-hotspots](https://github.com/colinmac-boop/tidycop-hotspots).

- **Script:** `web/scripts/predict_hotspots.py`. Reads the already-
  fetched `web/data/<slug>.json`, splits ~2/3 train / ~1/3 test by
  date, trains a `HotspotForest` (random-forest regressor), and
  writes `web/data/<slug>_hotspots.geojson` — top 10% of
  positive-risk cells, ~55 cells for Chicago at 300 m.
- **Adding a city:** add one dict entry to `HOTSPOT_CONFIG` at the
  top of `predict_hotspots.py`:
  ```python
  HOTSPOT_CONFIG = {
      "chicago":    {"cell_size_m": 300, "bandwidth_m": 500, "top_pct": 0.10},
      "detroit":    {"cell_size_m": 250, "bandwidth_m": 400, "top_pct": 0.10},
      # ...
  }
  ```
- **Frontend:** `generate_site.py` emits identical JS on every
  page; the JS tries to fetch the hotspots GeoJSON and silently
  no-ops on 404. So new cities light up automatically once they
  have a hotspots file.
- **Validation:** PAI@10% is printed at training time and stored
  in the GeoJSON `properties.metrics` so it's visible from the
  page's "What is this?" popup.
- **Method reference:** Wheeler & Steenbeek (2021), "Mapping the
  Risk Terrain for Crime Using Machine Learning," *Journal of
  Quantitative Criminology* 37(2): 445-480.

## Scheduled refresh

Weekly automatic refresh via launchd (Mondays 06:00 America/New_York):

- Wrapper: `scripts/refresh_site.sh` (fetch + predict + generate + `vercel --prod`)
- launchd job: `scripts/us.citycrimemap.refresh.plist`
- Logs: `logs/refresh.log` (rotates at 2 MB), `logs/launchd.{out,err}`
- Single-instance lock via `flock` on `logs/refresh.lock`

Install:

```bash
cp scripts/us.citycrimemap.refresh.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/us.citycrimemap.refresh.plist
launchctl list | grep citycrimemap   # should show the job
```

The refresh path is **token-free**: tidycop + tidycop-spotcrime are
rule-based (no LLM calls anywhere). The only network calls are to
city open-data portals (Socrata / ArcGIS / CKAN), the U.S. Census
geocoder for cities in `geocode.CITY_CONFIGS`, and Vercel.

## Known limitations

- Seattle still has ~16% Unclassified after the 2026-06-28 classifier
  pass: drugs/DUI/all-other-offenses don't fit the 8 SpotCrime
  buckets. These are visible-but-grey on the map.
- Tables cap at 1,500 incidents per city per fetch to keep
  `/data/<slug>.json` browser-friendly (largest is Chicago at ~176 KB).

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
