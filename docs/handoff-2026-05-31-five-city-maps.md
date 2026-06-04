# Handoff — Five-city crime map pages with SpotCrime alerts CTA

**Date:** 2026-05-31
**From:** Anwen (tidycop maintainer)
**To:** Feraindo (`main` agent, `~/.openclaw/workspace`)
**Reason for handoff:** product/frontend work — not tidycop's house

---

## The ask (from Colin, 2026-05-31)

> "create five city crime maps and information tables, with a sign up
> for spotcrime alerts call to action on the page."

## Why this isn't tidycop's job

Same boundary as the 2026-05-29 Boise cleanup: tidycop is city-agnostic
data infrastructure. Map pages and a SpotCrime-branded CTA are
product/frontend concerns. They belong under `~/.openclaw/workspace/`
(or wherever your web staging lives), consuming tidycop as a library.

See `AGENTS.md` § "Hard Boundary" for the canonical statement.

## What tidycop gives you

- `get_incidents(city, start_date, end_date)` → normalized DataFrame
  with 23 `std_*` columns. Map-ready fields:
  - `std_lat`, `std_lng`
  - `std_datetime`
  - `std_offense_description`
  - `std_address`
- 25 upstream-parity cities: chicago, seattle, san_francisco,
  pittsburgh, detroit, dallas, cincinnati, providence, gainesville,
  fort_lauderdale, cleveland, rochester, boston, hartford,
  indianapolis, denver, minneapolis, grand_rapids, naperville,
  houston, washington_dc, kansas_city, new_orleans, san_antonio,
  new_york.
- Boise is **not** in the default registry. It's in your overlay at
  `~/.openclaw/workspace/spotcrime_sources/cities.yaml`. Use
  `registry_path=` (Python) or `--registry-path` (CLI) to load it.
- Current release: tidycop v0.3.0.

## Bucket classification (optional)

`tidycop-spotcrime` v0.1.0 ships the 8-category classifier (Shooting /
Robbery / Assault / Burglary / Theft / Arson / Vandalism / Arrest).
Install with `pip install tidycop-spotcrime`, then pass
`classify_spotcrime=True` to `get_incidents` (Python) or
`--classify-spotcrime` (CLI).

**Coverage gotcha:** in v0.2.0 only the 5 MVP cities ship a populated
`spotcrime_category_map` (chicago, seattle, san_francisco, pittsburgh,
dallas — confirm in `registry/cities.yaml`). The other 20 cities have
empty maps and will return null/unclassified buckets. If you want
classified rows on the info table, prefer the MVP 5.

## Starter snippets

Python:
```python
from tidycop import get_incidents

df = get_incidents(
    "chicago",
    start_date="2026-05-24",
    end_date="2026-05-31",
)
# df.columns includes std_lat, std_lng, std_datetime,
# std_offense_description, std_address, std_incident_id, ...
```

With classifier:
```python
df = get_incidents(
    "chicago",
    start_date="2026-05-24",
    end_date="2026-05-31",
    classify_spotcrime=True,  # requires tidycop-spotcrime installed
)
```

With your Boise overlay:
```python
df = get_incidents(
    "boise",
    start_date="2026-05-24",
    end_date="2026-05-31",
    registry_path="/Users/mac/.openclaw/workspace/spotcrime_sources/cities.yaml",
)
```

CLI:
```sh
tidycop fetch chicago --start 2026-05-24 --end 2026-05-31 --output chicago.csv
tidycop fetch boise --start 2026-05-24 --end 2026-05-31 \
  --registry-path ~/.openclaw/workspace/spotcrime_sources/cities.yaml \
  --output boise.csv
```

## What I won't do from the tidycop seat

- Pick the five cities for you. (My guess: top SpotCrime markets > upstream-parity-only, but you know the product traffic.)
- Write CTA copy or wire the SpotCrime alerts signup endpoint.
- Add new cities to `registry/cities.yaml` for this. If you need a non-upstream city, it goes in your overlay. The pre-commit guard at `scripts/check_no_downstream_cities.py` will block it anyway.
- Build the HTML / map JS / info table layout.

## What I will help with on request

- Schema questions (what does `std_*` actually contain for city X?)
- A city's offense vocabulary or NIBRS coverage
- Dedup behavior (`tidycop/dedup.py`, SHA-256 over `std_*` minus provenance)
- Source-window selection (e.g. cincinnati legacy→current, cleveland legacy→P1RMS)
- Anything else where the answer lives inside `~/Projects/tidycop/`

Ping me by having Colin relay (cross-agent `sessions_send` is firewalled
from my seat by design).

— Anwen 📚
