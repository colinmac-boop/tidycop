# City rollout plan — citycrimemap.us (20 → 25)

**Decision (Colin 2026-06-04 10:41 EDT):** Option C. Classify before
shipping. Roll out in waves. Keep moving.

This plan ranks the 20 unmapped cities by *classifiability* — how
clean the upstream taxonomy is and how much per-city mapping work
the SpotCrime 8-bucket scheme will need before each city can ship
without "Unclassified" being the dominant category.

Survey ran 2026-06-04; results live in `/tmp/survey_out.json` /
`/tmp/survey_log.txt`. Re-run with
`.venv/bin/python /tmp/survey_cities.py` if you need fresher numbers.

## Tier 1 — Fast wins (Wave 1)

Cities where `std_offense_category` is small and already SpotCrime-shaped.
Each is maybe 30 minutes of YAML.

| City | Rows / 21d | Unique cats | Why it's fast |
|---|---|---|---|
| **washington_dc** | 1,324 | 9 | All 9 categories map cleanly: `THEFT/OTHER` `THEFT F/AUTO` `MOTOR VEHICLE THEFT` `ASSAULT W/DANGEROUS WEAPON` `ROBBERY` `BURGLARY` `SEX ABUSE` `ARSON` `HOMICIDE`. 100% coverage achievable. |
| **houston** | 2,000 | 11 | NIBRS-clean. Top: `Simple assault` `Intimidation` `Aggravated Assault`. Maps straight onto Assault + a handful of others. |
| **san_antonio** | 2,000 | 19 | NIBRS standard names: `Larceny/Theft Offenses`, `Assault Offenses`, `Destruction/Damage/Vandalism of Property`, `Breaking & Entering`, `Motor Vehicle Theft`. Textbook. |
| **rochester** | 267 | 5 | Tiny taxonomy: `Larceny`, `Motor Vehicle Theft`, `Aggravated Assault`, `Burglary`, `Robbery`. Five lines of YAML. |
| **cleveland** | 2,000 | 56 → ~25 useful | Standard NIBRS descriptions; the long tail is noise. Top 15 cover most volume. |

**Goal:** ship all 5 of these in week 1. That puts citycrimemap.us at
**10 cities live** by 2026-06-11 ish.

## Tier 2 — NIBRS-descriptive, medium effort (Wave 2)

Cities with clear taxonomies but more categories to map (~30-60). Each
is maybe 1-2 hours.

| City | Rows / 21d | Unique cats | Notes |
|---|---|---|---|
| **boston** | 2,000 | 45 | Mix of useful (`SIMPLE ASSAULT`, `VANDALISM`, `DRUG VIOLATION`) and non-criminal (`MEDICAL ASSISTANCE`, `MV CRASH RESPONSE`, `TOWED`). Need to bucket non-criminal as `null` so they get filtered out. |
| **indianapolis** | 2,000 | 60 | NIBRS-rich: `Simple Assault`, `Vandalism Under $2500 No Hate Crime`, `Motor Vehicle Theft`, `Burglary`, `Aggravated Assault`. Hate-crime modifier rows need bucketing. |
| **hartford** | 1,888 | 31 | NIBRS proper (`DESTRUCTIVE/DAMAGE/VANDALISM OF PROPERTY`, `SIMPLE ASSAULT`, `MOTOR VEHICLE THEFT`, `BURGLARY/BREAKING AND ENTERING`). 43% are `NOT NIBRS REPORTABLE` — bucket to `null`. |
| **minneapolis** | 1,448 | 29 | Uses opaque short codes: `AUTOTH` (auto theft), `TFMV` (theft from motor vehicle), `BURGD` (burglary dwelling), `ASLT2` (assault 2nd). Need a code-decode pass first. |

**Goal:** ship in week 2. By ~2026-06-18: **14 cities live**.

## Tier 3 — Taxonomy quirks, longer effort (Wave 3)

Cities where the data is good but the taxonomy needs more decoding.

| City | Rows / 21d | Notes |
|---|---|---|
| **dallas** | 2,000 | Only 3 categories — `A`, `B`, `C`. Useless. Have to classify off `std_offense_description` (205 unique strings) instead. Doable, just verbose. |
| **denver** | 1,937 | 13 cats but `all-other-crimes` and `public-disorder` are too coarse; need to drop down to descriptions (102 unique) to pull out arrests vs. crimes. |
| **gainesville** | 858 | `std_offense_category` is empty — classify off description (121 unique strings). `Theft Petit - Retail`, `Battery (simple)`, `Burglary to Conveyance` — clear once mapped. |
| **cincinnati** | 1,358 | Categories are administrative (`Part 1 Property`, `Part 2`, `Part 1 Violent`) not crime types. Need description-level mapping (10 unique). |
| **providence** | 835 | 97 categories — most are full RI statute strings like `LARCENY/U $1500 - FROM MV`. Will need pattern-matching, not exact match. |
| **new_orleans** | 2,000 | 91 categories. Lots of non-incident noise (`AREA CHECK`, `BUSINESS CHECK`, `COMPLAINT OTHER`, `TRAFFIC INCIDENT`). Need aggressive filtering. |

**Goal:** ship in weeks 3-4. By ~2026-07-02: **20 cities live**.

## Tier 4 — Blocked at the source

Cities I can't ship until something upstream changes. These get
flagged for Colin, not worked on.

| City | Problem |
|---|---|
| **san_antonio** | SAPD CKAN dataset publishes only `Zip_Code` (no lat/lng, no street address). Classifier map is in place (83% classified on 3,000 rows) so the library is useful, but Leaflet needs coordinates so the frontend can't render. Need a geocoded SA feed; meanwhile zip-level aggregation would be the only way to put SA on a map. (Discovered 2026-06-04 during Wave 1 deploy.) |
| **boston** | ArcGIS `Boston_Incidents_View` is `type=Table` with no geometry and no Lat/Long columns (only `BLOCK` street-string). Can't render markers without geocoding. There's a richer `data.boston.gov` CKAN dataset that does include Lat/Long, but it's not in upstream R `tidycops` so adding it would violate the boundary. Library entry stays; frontend deferred. (Discovered 2026-06-04 during Wave 2 deploy.) |
| **fort_lauderdale** | Upstream Socrata feed stopped 2022-09-18. Likely city retired the dataset. Tidycop registry shows it as the only source. Need to either find a replacement dataset or drop the city from the site. |
| **naperville** | Upstream ArcGIS layer stopped 2024-12-01. Same story — find replacement or drop. |
| **new_york** | NYPD Socrata complaint feed (`5uac-w243`) returned 0 rows for last 21 days. Either the feed is severely lagged or our query is wrong. Need investigation; NYPD has notoriously slow publishing. |
| **kansas_city** | KCPD Socrata returned 0 rows for last 21 days. Same investigation needed; KC has 12 per-year layers in tidycop, the active-window selection might be picking a stale one. |
| **grand_rapids** | ArcGIS returned 0 rows for last 21 days. Investigation needed. |

**Action:** I'll file these as a separate "frontend can't render these
yet" issue and keep investigating in parallel with classifier work.
For tidycop the library, these cities are still valid — the parity
contract is the registry entries, not "must currently return rows."

## Per-wave workflow

For each city in a wave:

1. **Pull a fresh sample** via `tidycop.get_incidents(city, 21d, view="comparable")`.
2. **Distinct-offense survey** — list the top-50 `std_offense_category`
   values by frequency, with row count.
3. **Bucket the top-N** so I cover ≥90% of rows. The long tail (singleton
   weird offenses) is fine to leave as `null` / Unclassified.
4. **Open PR against `~/Projects/tidycop`** that adds the
   `spotcrime_category_map` block to that city's source(s) in
   `registry/cities.yaml`.
5. **Smoke test:** `tidycop fetch <city> --classify-spotcrime --start <X> --end <Y>` — assert >80% rows classified.
6. **Add city** to `web/scripts/cities.py` (key, slug, map center,
   window_days, alerts URL).
7. **Refresh + redeploy:** `web/scripts/fetch_data.py` →
   `generate_site.py` → `cd web/pages && vercel --prod`.
8. **Smoke-test the live URL:** `curl -sI` + visual check.

The `web/scripts/cities.py` step and the YAML map step are the only
two writes. Everything else is verification.

## Index page

When we cross 10 cities, "Five-City Crime Maps" title needs to come
out. Suggested rename: just **"City Crime Maps"** (the domain name).
Subtitle becomes dynamic: *"Crime maps for {N} US cities."* Doing this
in Wave 1 so the title isn't a moving target.

## Risks / open questions

- **Vercel rate limit.** Wave 1 = 5 deploys in a week. Should be fine
  on a free Vercel tier. If we hit limits I'll batch waves into single
  deploys.
- **`tidycop-spotcrime` release cadence.** Right now the classifier
  package is `v0.1.0` GitHub-source-install. Map changes ship from
  tidycop (registry YAML), not from the classifier package, so this
  isn't blocking. But a `tidycop-spotcrime` v0.2.0 PyPI release would
  be nice once the dust settles.
- **Per-city map centers and zoom.** I'll pick reasonable defaults
  (city hall lat/lng, zoom 11). If anything looks off after deploy,
  it's a one-line fix in `web/scripts/cities.py`.
- **Alerts URLs.** SpotCrime alerts pattern is
  `https://spotcrime.com/<state>/<city>` — works for the 5 cities we
  have. Need to validate for each new city before linking.

## Status tracker

Living checklist; tick as we ship.

- [x] **Wave 1:** washington_dc, houston, rochester, cleveland (san_antonio classified but blocked by no-coords; see Tier 4)
- [x] **Wave 2:** indianapolis, hartford, minneapolis (boston blocked by no-coords; see Tier 4)
- [x] **Wave 3:** cincinnati, gainesville, denver (2026-06-05). dallas / providence / new_orleans bumped to Tier 4 — all three publish without lat/lng.
- [ ] **Blocked:** dallas, providence, new_orleans, fort_lauderdale, naperville, new_york, kansas_city, grand_rapids, san_antonio, boston
- [x] Index-page rename "Five-City Crime Maps" → "City Crime Maps"

Updated daily-log entries: `memory/2026-06-04.md` (this plan filed).
