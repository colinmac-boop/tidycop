# SEO plan — citycrimemap.us

Drafted 2026-06-28. Owner: Anwen. Reviewer: Colin.

## Goal

Make citycrimemap.us the best-indexed crime-map site for the public-data-driven US crime-map query universe — the queries that today route to crimemapping.com, crimegrade.org, communitycrimemap.com, and cityprotect.com.

Concrete success criteria, 6-month horizon:

- Rank top-5 for `<city> crime map` for each of the 16 live cities.
- Rank top-10 for `crime in <neighborhood>, <city>` for at least 50 neighborhood pages spanning the live cities.
- 10k organic monthly clicks across the site (GSC).
- One unambiguous brand keyword owned: `citycrimemap` returns us at #1.

The plan is built around one observation: of the four competitors, only one of them has a real SEO surface. That's the lane.

## Competitor structural audit

| Competitor | Architecture | Per-city pages? | Per-neighborhood pages? | SEO posture |
|---|---|---|---|---|
| **crimemapping.com** (CentralSquare) | JS SPA + agency-iframe model. Each PD links to it; the PD URL ranks, not crimemapping.com itself. | URL slugs like `/map/ca/SanJose` exist but render as a hashed JS shell with no crawlable map state. | No | Brand-keyword dominant, organic body weak. Lives on PD inbound links. |
| **crimegrade.org** | Static per-area pages, machine-generated. ZIP- and neighborhood-grain. Heavy editorial-style copy ("1 in 142 chance"), monetized with home-security affiliate links. | Yes, every city. | Yes, every ZIP and many named neighborhoods. | The only real organic player in the set. Comparable, beatable. |
| **communitycrimemap.com** (LexisNexis) | JS SPA, single canonical URL, login wall on most features. | No | No | Almost no SEO surface. |
| **cityprotect.com** (Motorola) | JS SPA, single canonical URL. | No | No | Same. |

**Implication:** the three vendor competitors don't actually compete on organic search — they compete on PD contracts. Our real opponent is **crimegrade.org**. Crimegrade beats us today on volume (every city + every ZIP). It loses to us on three structural axes we can press: live data freshness, transparent methodology, and no affiliate clutter.

## Wedges we can press

1. **Freshness.** Crimegrade rebuilds annually-ish from aggregated FBI / public sources. We refresh weekly from each city's live open-data portal (post-2026-06-28 launchd job). Surface it everywhere: "Updated weekly. Last refresh: 2026-06-28." Add a `<meta name="last-refreshed">` tag and structured-data `dateModified`. A "Last updated" date is the single strongest freshness signal Google reads.

2. **Methodology transparency.** Crimegrade's "machine learning fills the gaps" language is opaque. We can publish exactly what we do: the upstream `tidycop` library, the 8-category SpotCrime classifier (`tidycop-spotcrime`), the per-city map from `registry/cities.yaml`. One `/methodology` page that walks through it, with code links to GitHub, becomes both an SEO asset (long-form, technical, links-worthy) and a trust asset.

3. **No affiliate clutter.** Crimegrade injects "best home security" affiliate copy on every page. We don't. Cleaner page = better bounce + dwell metrics, both of which Google increasingly rewards.

4. **Open source.** `tidycop` + `tidycop-spotcrime` on GitHub. Researchers, journalists, civic-tech orgs link to us as the data source for their own work. Backlinks from `.edu` / `.gov` / `.org` are the long-tail compounder.

## What we do NOT do

These are not part of the plan even though they'd help on paper:

- **Buy paid links / PBN networks.** Spam. Long-term liability. Not Colin's lane and not mine.
- **Spin up programmatic ZIP pages without data.** Crimegrade does this and Google has tolerated it; if we ship empty-frame ZIP pages with no real incident overlay we'll get classified as doorway pages. Every ZIP/neighborhood page we ship must render real incidents from the live feed.
- **Outrank PD official sites.** Most cities link their own residents to the PD's own crime page. We don't try to displace those; we try to be the cross-city aggregator alternative, the one anyone moving / comparing cities goes to.
- **Sneak SpotCrime CTAs into copy.** The existing SpotCrime alerts link per city is fine (and predates the SEO push). New SEO copy should not turn into SpotCrime marketing. Search engines smell it and penalize.

## On-page work (tracked, can be tackled in order)

### Phase 1 — fix the basics (1-2 days work, immediate)

- **Add `<meta name="description">`** to every page. Currently absent. Per-city template: "Live crime map and recent incident list for <City>, <State>. Data refreshed weekly from <City PD source name>. <N> incidents in the last <window_days> days." 150-160 chars.
- **Add Open Graph + Twitter card tags.** `og:title`, `og:description`, `og:image`, `og:url`, `og:type=website`, `twitter:card=summary_large_image`. The `og:image` per city should be a static PNG snapshot of the city's map (one-off generation per refresh — can pre-render with Playwright or accept a generic city-skyline image to start).
- **`<title>` tag rewrite.** Current Boston title is "City Crime Map — Boston" (or similar). Better: "Boston Crime Map — Live Incidents Updated Weekly". Format: `<City> Crime Map — Live Incidents Updated Weekly | CityCrimeMap`. Keeps the brand last (Google truncates at ~60 chars; lead with the query intent).
- **`<h1>`** per city: "<City> Crime Map" — explicit, matches search intent.
- **JSON-LD structured data:** `WebPage` with `dateModified` set to the fetch timestamp. Optional: `Dataset` schema declaring our snapshot as a dataset with source citation. Crimegrade does not do this.
- **Sitemap.** Generate `sitemap.xml` listing all city pages + future neighborhood pages, with accurate `<lastmod>` per refresh. Submit to GSC + Bing Webmaster.
- **robots.txt.** Currently absent (presumably). Allow all, point at sitemap.
- **Canonical URLs.** Already wired via `BASE_URL`. Audit that every page emits one.

### Phase 2 — content that ranks (1-2 weeks, biggest lift)

- **Per-city methodology / data-source block** below the map. Currently the only context is "Data source: <link>". Expand to 2-3 paragraphs: which dataset, what window, how the classifier maps the city's native categories into the 8 SpotCrime buckets, what gets dropped (e.g. Seattle's "Not Reportable to NIBRS"). 300-400 words of unique, fact-grounded copy per city is enough to clear "thin content" without keyword-stuffing.
- **`/methodology` page.** Long-form explanation of `tidycop` + `tidycop-spotcrime` + the registry. Links to GitHub. ~1500 words. This is the single page most likely to attract backlinks.
- **`/sources` page.** A list of every open-data portal we pull from, with city + dataset ID + portal link + refresh window. This is the page journalists and researchers link to.
- **`/about` page.** Short. Who runs this (Colin / SpotCrime, briefly), why it's free, how often it updates, no affiliate disclosure needed because there are no affiliates.

### Phase 3 — neighborhood pages (weeks 3-6, the volume play)

This is where we go from 16 indexed pages to 500+. One template, fed by a neighborhoods registry.

Approach:

- For each live city, define a `neighborhoods.yaml` block with `{ name, slug, polygon: [[lat, lng], ...] }`. Start with the 10-20 best-known neighborhoods per city (Wikipedia + city planning department often publishes shapefiles).
- At fetch time, point-in-polygon the city's incidents into each neighborhood. Emit `/{city}/{neighborhood}.html` with the same map + table component, filtered.
- Per-page copy template: "<Neighborhood> is a neighborhood of <City>, <State>. In the last <window_days> days, <N> incidents have been reported within its boundaries. The most common categories were <top-3 cats>." Plus a small block linking to adjacent neighborhoods (internal link graph; Google loves a real one).
- **Only ship a neighborhood page if it has ≥10 incidents in the window.** No empty-frame doorway pages. Skip rural fringes.

Target: 250-400 neighborhood pages across the 16 live cities by week 6.

### Phase 4 — query expansion (ongoing, low priority)

- **Comparison pages.** `/<city-a>-vs-<city-b>-crime` for the top 25 same-state and rivalry pairings. Programmatic but limited to where both cities are live. Easy traffic on relocation-research queries.
- **Category landing pages.** `/<city>/theft`, `/<city>/shooting`, etc. Only for cities where the category has ≥20 incidents in the window. Same template, filtered to one category, with a 200-word copy block.
- **Annual recap pages.** Once we have 12 months of refreshes archived, ship `/<city>/2026-year-in-review` etc. Annual recap is link-bait.

## Technical SEO work (Phase 1, parallel)

- **Core Web Vitals.** Currently the page loads Leaflet + a large JSON blob. Likely fine on LCP (no images above-the-fold) but the JSON parse is on the critical path. Audit via PageSpeed Insights after Phase 1 ships and decide if we need to defer the JSON load until after first paint.
- **No JS-blocking renders.** Tailwind + Leaflet are both CDN-hosted, which is fine for performance but means we depend on those CDNs being indexable. Add `<noscript>` content that shows the incident table without the map — Google's bot does render JS but a static fallback removes risk.
- **`hreflang`.** Not relevant (US-only, English-only).
- **HTTPS + HSTS.** Vercel does HTTPS by default; HSTS is on by default for `.us`. Confirm via securityheaders.com.
- **404 + 410 hygiene.** When we drop a city (fort_lauderdale, naperville), serve 410 not 404 + a polite explanation. Never let dropped cities serve soft-404 200s with empty data.

## Off-page work

- **GitHub README badges and links** that point at citycrimemap.us from both `tidycop` and `tidycop-spotcrime` README files. We already have this in `pyproject.toml` URLs; cross-pollinate to README.
- **One blog post per quarter** on the methodology blog (TBD). Topics: "How we classify NIBRS for SpotCrime", "Why Seattle's classifier is hard", "Mapping addresses with the Census geocoder". Each is naturally link-worthy for civic-tech audiences.
- **Reddit/HN seeding strategy:** none. Don't do this. Submit `tidycop` to civic-tech aggregators when v0.4.0 ships (e.g. `civic-tech-news`, `open-data-news`) as a genuine release, not as a citycrimemap promo.
- **Internal linking from `spotcrime.com`.** Worth a conversation with Colin — does SpotCrime want to link to citycrimemap.us as a "research view" or similar? If yes, that's a domain-level boost. If no, fine.

## Measurement

Set up before any Phase 2 work ships:

- **Google Search Console** verified on citycrimemap.us. Track impressions/clicks/CTR/position by query.
- **Bing Webmaster Tools** same.
- **Analytics — decided 2026-07-08:** shipped **Google Analytics 4** (measurement id `G-H7TPDESB8N`), overriding the plan's original "no GA" stance. Rationale from Colin: GA4 pairs cleanly with Search Console (same account, one dashboard for organic + on-site), and the privacy cost is mitigated by `anonymize_ip: true` and no PII collection. The tag is wired via `GA4_ID` env var in `web/scripts/generate_site.py`; set `GA4_ID=""` to disable for local builds. Plausible / Fathom / Vercel Analytics remain viable second sources if we ever want a privacy-first mirror, but adding a second analytics vendor is out of scope until GA4 has run long enough to establish baseline (target: 2026-08).
- **Weekly review** of the GSC "Pages" report. Cheap signal for what's getting indexed vs. crawled-not-indexed.

Baseline metrics to capture week 1 so we can show movement:

- Indexed page count
- Total impressions (rolling 28 days)
- Top 20 queries

## Suggested execution sequence

| Phase | Effort | Order | Why this order |
|---|---|---|---|
| Phase 1 (basics) | 1-2 days | First | Cheapest, biggest immediate visibility lift. Nothing else works until per-page meta is right. |
| Measurement | 2 hours | Right after Phase 1 | Establish baseline before content changes. |
| Phase 2 (content) | 1-2 weeks | Second | Lifts every page on quality + dwell. Required before neighborhood pages or Google will see those as thin. |
| Phase 3 (neighborhoods) | 3-4 weeks | Third | The volume play. Pays back over months. |
| Phase 4 (query expansion) | Ongoing | Last | Diminishing returns; don't start before Phase 3 stabilizes. |

## Open questions for Colin

1. ~~**Vercel Analytics vs. Plausible?**~~ **Resolved 2026-07-08:** GA4 shipped instead (see Measurement section).
2. **SpotCrime ↔ CityCrimeMap cross-link.** Worth doing for SEO + topical authority. Wants your call.
3. **Methodology blog domain.** Sub-path (`citycrimemap.us/blog`) or subdomain (`blog.citycrimemap.us`)? Sub-path is better for SEO consolidation; subdomain is easier to manage as a separate Vercel project. Defaulting to sub-path unless you push back.
4. **Affiliate revenue.** Crimegrade monetizes via home-security affiliates. Want to consider that route at all, or stay clean? My default reading is stay clean — affiliate clutter is one of our wedges against them.

## Out of scope for this plan

- Mobile app. The PWA conversation is separate; this plan covers static web SEO only.
- Paid acquisition (Google Ads). Same.
- Email capture / newsletter. Same.
- Real-time push notifications. SpotCrime alerts handle that; we deep-link to them per city already.

---

*This plan supersedes nothing — it's the first formal SEO writeup for citycrimemap.us. Update / revise in this same file as phases ship; capture each phase's actual results in `memory/YYYY-MM-DD.md`.*
