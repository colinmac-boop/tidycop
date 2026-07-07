#!/usr/bin/env python3
"""Generate the static site (index + per-city pages) from data/*.json.

Output: web/pages/index.html, web/pages/<slug>.html, web/pages/about.html,
web/pages/faq.html, web/pages/robots.txt, web/pages/sitemap.xml, and a
copy of /data/<slug>.json into web/pages/data/.

After running, web/pages/ is the static-deployable site root.

SEO notes
---------
Per-city pages are the primary organic-search target ("chicago crime map",
"seattle crime map near me", etc.). Each page carries:

- unique <title>/description/keywords crafted from the city + fresh
  category counts;
- <link rel="canonical"> pinned to the citycrimemap.us URL;
- Open Graph + Twitter Card meta so shared links render richly;
- JSON-LD: WebSite (index only), Organization, BreadcrumbList, and a
  Dataset entity describing the incident feed;
- a server-rendered "recent incidents" preview so Google sees real
  content even before the map JS loads;
- FAQPage JSON-LD on faq.html for rich snippets.

Two hooks let ops swap in real IDs without touching this file:

- GA4_ID env var → adds the Google tag (gtag.js) with that measurement id.
- GSC_VERIFICATION env var → adds the Search Console verification meta.
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "pages"
OUT_DATA_DIR = OUT_DIR / "data"

# Canonical domain for SEO (og:url, <link rel="canonical">).
# Override via env: BASE_URL=https://citymaps.vercel.app python generate_site.py
BASE_URL = os.environ.get("BASE_URL", "https://citycrimemap.us").rstrip("/")

# Google Analytics 4 measurement id (e.g. "G-XXXXXXXXXX"). If unset,
# no analytics script is emitted (safe default for local builds).
GA4_ID = os.environ.get("GA4_ID", "").strip()

# Google Search Console verification token (the value of the
# "content" attribute Google gives you for the meta-tag method).
GSC_VERIFICATION = os.environ.get("GSC_VERIFICATION", "").strip()

# Static OG image path (generated separately; see scripts/make_og_image.py).
OG_IMAGE = "/og-image.png"

# Site tagline used across pages
SITE_NAME = "CityCrimeMap"
SITE_TAGLINE = "Free interactive crime maps for major US cities"

CATEGORY_COLORS = {
    "Shooting": "#7f1d1d",     # dark red
    "Robbery": "#dc2626",      # red
    "Assault": "#ea580c",      # orange
    "Burglary": "#ca8a04",     # amber
    "Theft": "#0891b2",        # cyan
    "Arson": "#be185d",        # pink-red
    "Vandalism": "#7c3aed",    # violet
    "Unclassified": "#475569", # slate
}

# ─── Head / meta ─────────────────────────────────────────────────────────

def _analytics_snippet() -> str:
    if not GA4_ID:
        return ""
    return f"""
  <!-- Google tag (gtag.js) -->
  <script async src="https://www.googletagmanager.com/gtag/js?id={GA4_ID}"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', '{GA4_ID}', {{ 'anonymize_ip': true }});
  </script>
"""


def _gsc_meta() -> str:
    if not GSC_VERIFICATION:
        return ""
    return f'\n  <meta name="google-site-verification" content="{GSC_VERIFICATION}">'


def head(
    title: str,
    description: str,
    canonical: str,
    *,
    keywords: str = "",
    og_type: str = "website",
    json_ld: list[dict] | None = None,
) -> str:
    kw = f'\n  <meta name="keywords" content="{keywords}">' if keywords else ""
    ld_block = ""
    if json_ld:
        for obj in json_ld:
            ld_block += (
                '\n  <script type="application/ld+json">'
                + json.dumps(obj, separators=(",", ":"))
                + "</script>"
            )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="robots" content="index,follow,max-image-preview:large">
  <meta name="theme-color" content="#b91c1c">{_gsc_meta()}
  <title>{title}</title>
  <meta name="description" content="{description}">{kw}
  <link rel="canonical" href="{canonical}">

  <!-- Open Graph -->
  <meta property="og:site_name" content="{SITE_NAME}">
  <meta property="og:title" content="{title}">
  <meta property="og:description" content="{description}">
  <meta property="og:type" content="{og_type}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:image" content="{BASE_URL}{OG_IMAGE}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">

  <!-- Twitter Card -->
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{title}">
  <meta name="twitter:description" content="{description}">
  <meta name="twitter:image" content="{BASE_URL}{OG_IMAGE}">

  <!-- Icons -->
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="/apple-touch-icon.png">

  <!-- Perf hints -->
  <link rel="preconnect" href="https://unpkg.com" crossorigin>
  <link rel="preconnect" href="https://cdn.tailwindcss.com" crossorigin>
  <link rel="preconnect" href="https://tile.openstreetmap.org" crossorigin>
  <link rel="dns-prefetch" href="https://spotcrime.com">

  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {{ theme: {{ extend: {{ colors: {{
      brand: {{ 50:'#fef2f2', 100:'#fee2e2', 500:'#ef4444', 600:'#dc2626', 700:'#b91c1c', 800:'#991b1b' }}
    }} }} }} }};
  </script>
  <style>
    .leaflet-container {{ background:#1f2937; }}
    .legend-dot {{ width: 0.75rem; height: 0.75rem; border-radius: 9999px; display:inline-block; margin-right:0.4rem; vertical-align:middle; }}
  </style>{ld_block}{_analytics_snippet()}
</head>
"""


# ─── Nav / footer / CTA ──────────────────────────────────────────────────

def nav(active_slug: str | None, summary: list[dict], *, static_active: str | None = None) -> str:
    """Global nav. `active_slug` marks a city page; `static_active` marks
    a top-level static page ("home", "about", "faq")."""
    all_cls = "font-bold text-white" if (static_active == "home") else "text-brand-100/80 hover:text-brand-100"
    items = [f'<a href="/" class="{all_cls}">All cities</a>']
    for c in summary:
        cls = "font-bold text-white" if c["slug"] == active_slug else "text-brand-100/80 hover:text-brand-100"
        items.append(f'<a href="/{c["slug"]}" class="{cls}">{c["name"]}</a>')
    about_cls = "font-bold text-white" if static_active == "about" else "text-brand-100/80 hover:text-brand-100"
    faq_cls = "font-bold text-white" if static_active == "faq" else "text-brand-100/80 hover:text-brand-100"
    items.append(f'<a href="/about" class="{about_cls}">About</a>')
    items.append(f'<a href="/faq" class="{faq_cls}">FAQ</a>')
    return f"""
<header class="bg-brand-700 text-white">
  <div class="max-w-7xl mx-auto px-4 py-4 flex flex-wrap items-center justify-between gap-4">
    <a href="/" class="text-xl font-bold tracking-tight" aria-label="{SITE_NAME} home">🚨 {SITE_NAME}</a>
    <nav class="flex flex-wrap gap-x-5 gap-y-1 text-sm" aria-label="Primary">
      {''.join(items)}
    </nav>
  </div>
</header>
"""


def alerts_cta(city_name: str, alerts_url: str) -> str:
    return f"""
<section class="bg-gradient-to-br from-brand-700 to-brand-800 text-white">
  <div class="max-w-5xl mx-auto px-4 py-12 text-center">
    <p class="uppercase tracking-widest text-xs text-brand-100/80 mb-2">Free email alerts</p>
    <h2 class="text-3xl md:text-4xl font-bold mb-3">Get {city_name} crime alerts in your inbox</h2>
    <p class="text-brand-100 text-base md:text-lg max-w-2xl mx-auto mb-6">
      SpotCrime sends a daily email with crimes reported near any address you choose.
      Free, no app required, unsubscribe anytime.
    </p>
    <a href="{alerts_url}" target="_blank" rel="noopener"
       class="inline-flex items-center gap-2 bg-white text-brand-700 px-7 py-3 rounded-lg font-bold text-base md:text-lg shadow hover:bg-red-50 transition">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path></svg>
      Sign up for {city_name} alerts on SpotCrime →
    </a>
    <p class="text-brand-100/70 text-xs mt-4">Opens spotcrime.com in a new tab.</p>
  </div>
</section>
"""


def footer(generated_at: str, n_cities: int) -> str:
    year = datetime.now(timezone.utc).year
    return f"""
<footer class="bg-slate-900 text-slate-300 mt-12">
  <div class="max-w-7xl mx-auto px-4 py-10 grid md:grid-cols-4 gap-6 text-sm">
    <div>
      <p class="font-bold text-white mb-2">🚨 {SITE_NAME}</p>
      <p class="text-slate-400">{SITE_TAGLINE}. Built on the open-source <a href="https://github.com/colinmac-boop/tidycop" class="text-brand-500 hover:text-brand-100" target="_blank" rel="noopener">tidycop</a> library — {n_cities} cities and growing.</p>
    </div>
    <div>
      <p class="font-bold text-white mb-2">Explore</p>
      <ul class="space-y-1 text-slate-400">
        <li><a class="hover:text-brand-100" href="/">All city crime maps</a></li>
        <li><a class="hover:text-brand-100" href="/about">About the data</a></li>
        <li><a class="hover:text-brand-100" href="/faq">FAQ</a></li>
        <li><a class="hover:text-brand-100" href="/sitemap.xml">Sitemap</a></li>
      </ul>
    </div>
    <div>
      <p class="font-bold text-white mb-2">Get crime alerts</p>
      <p class="text-slate-400"><a class="text-brand-500 hover:text-brand-100" href="https://spotcrime.com" target="_blank" rel="noopener">SpotCrime covers thousands of cities →</a></p>
      <p class="text-slate-500 text-xs mt-2">Daily email alerts for any US address. Free.</p>
    </div>
    <div>
      <p class="font-bold text-white mb-2">Data freshness</p>
      <p class="text-slate-400">Last generated: <span class="font-mono">{generated_at}</span></p>
      <p class="text-slate-500 text-xs mt-2">Data comes from city open-data portals and may lag the real world by days to weeks. For real-time alerts, sign up at <a class="text-brand-500 hover:text-brand-100" href="https://spotcrime.com" target="_blank" rel="noopener">SpotCrime</a>.</p>
    </div>
  </div>
  <div class="border-t border-slate-800 text-slate-500 text-xs">
    <div class="max-w-7xl mx-auto px-4 py-4 flex flex-wrap justify-between gap-3">
      <span>© {year} {SITE_NAME}. Data © respective city open-data portals.</span>
      <span>Not affiliated with any law enforcement agency.</span>
    </div>
  </div>
</footer>
</body></html>
"""


# ─── JSON-LD builders ────────────────────────────────────────────────────

def _org_ld() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Organization",
        "name": SITE_NAME,
        "url": f"{BASE_URL}/",
        "logo": f"{BASE_URL}{OG_IMAGE}",
        "sameAs": [
            "https://github.com/colinmac-boop/tidycop",
            "https://spotcrime.com/",
        ],
    }


def _website_ld() -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": SITE_NAME,
        "url": f"{BASE_URL}/",
        "description": SITE_TAGLINE,
    }


def _breadcrumb_ld(items: list[tuple[str, str]]) -> dict:
    """items: list of (name, url) in order."""
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
            for i, (name, url) in enumerate(items)
        ],
    }


def _dataset_ld(city: dict) -> dict:
    """Emit schema.org Dataset for the per-city incident feed. Helps
    Google Dataset Search index the page and improves E-E-A-T signals."""
    cat_names = list(city["category_counts"].keys())
    return {
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"Recent reported crime incidents — {city['city']}, {city['state_abbrev']}",
        "description": (
            f"{city['row_count']:,} reported crime incidents in {city['city']}, "
            f"{city['state_abbrev']} over the last {city['window_days']} days, "
            f"aggregated from the {city['data_source']}. Categories: "
            + ", ".join(cat_names) + "."
        ),
        "url": f"{BASE_URL}/{city['slug']}",
        "keywords": [
            f"{city['city']} crime map",
            f"{city['city']} crime data",
            f"crime in {city['city']}",
        ] + cat_names,
        "isAccessibleForFree": True,
        "license": "https://opendatacommons.org/licenses/by/",
        "creator": {
            "@type": "GovernmentOrganization",
            "name": city["data_source"],
            "url": city["data_source_url"],
        },
        "publisher": _org_ld(),
        "spatialCoverage": {
            "@type": "Place",
            "name": f"{city['city']}, {city['state_abbrev']}",
            "geo": {
                "@type": "GeoCoordinates",
                "latitude": city["map_center"][0],
                "longitude": city["map_center"][1],
            },
        },
        "temporalCoverage": f"P{city['window_days']}D",
        "distribution": [
            {
                "@type": "DataDownload",
                "encodingFormat": "application/json",
                "contentUrl": f"{BASE_URL}/data/{city['slug']}.json",
            }
        ],
    }


# ─── Server-rendered incident preview (for SEO) ──────────────────────────

def _incident_preview(incidents: list[dict], limit: int = 10) -> str:
    """Server-render the first N incidents as an HTML table so crawlers
    see real content, not just a JS shell. The full interactive table
    is populated by JS later and replaces this. We wrap in <noscript>-
    style pattern via id=preview which JS clears before rendering."""
    rows = []
    for inc in incidents[:limit]:
        cat = inc.get("category") or "Unclassified"
        color = CATEGORY_COLORS.get(cat, "#64748b")
        desc = (inc.get("description") or "").replace("<", "&lt;").replace(">", "&gt;")
        addr = (inc.get("address") or "").replace("<", "&lt;").replace(">", "&gt;")
        dt_raw = inc.get("datetime") or ""
        dt_short = dt_raw[:16].replace("T", " ") if dt_raw else "—"
        rows.append(
            f'<tr class="border-b border-slate-100">'
            f'<td class="px-3 py-2 text-slate-700 whitespace-nowrap">{dt_short}</td>'
            f'<td class="px-3 py-2"><span class="inline-flex items-center gap-1"><span class="legend-dot" style="background:{color}"></span>{cat}</span></td>'
            f'<td class="px-3 py-2 text-slate-700">{desc}</td>'
            f'<td class="px-3 py-2 text-slate-700">{addr}</td>'
            f"</tr>"
        )
    return "\n".join(rows)


# ─── Legend ──────────────────────────────────────────────────────────────

def legend(cats: dict[str, int]) -> str:
    items = []
    for cat, count in cats.items():
        color = CATEGORY_COLORS.get(cat, "#64748b")
        items.append(
            f'<span class="inline-flex items-center text-xs mr-3 mb-1"><span class="legend-dot" style="background:{color}"></span><span class="text-slate-700">{cat}</span><span class="text-slate-400 ml-1">({count})</span></span>'
        )
    return "<div class=\"flex flex-wrap\">" + "".join(items) + "</div>"


def _city_with_state(name: str, state: str) -> str:
    if name.endswith(f", {state}"):
        return name
    return f"{name}, {state}"


# ─── Index page ──────────────────────────────────────────────────────────

def index_page(summary: list[dict]) -> str:
    cards = []
    for c in summary:
        cats = c["category_counts"]
        top_cats = ", ".join(f"{k} ({v})" for k, v in list(cats.items())[:4])
        cards.append(f"""
        <a href="/{c['slug']}" class="block bg-white border border-slate-200 rounded-lg shadow-sm hover:shadow-md transition p-5">
          <div class="flex items-start justify-between mb-3">
            <h3 class="text-xl font-bold text-slate-900">{c['name']}, {c['state_abbrev']}</h3>
            <span class="text-xs font-mono text-slate-500">{c['row_count']:,} incidents</span>
          </div>
          <p class="text-sm text-slate-600 mb-3">Last {c['window_days']} days</p>
          <p class="text-xs text-slate-500"><span class="font-semibold">Top categories:</span> {top_cats}</p>
          <p class="text-brand-600 text-sm font-semibold mt-3">View {c['name']} crime map →</p>
        </a>""")
    n = len(summary)
    city_list_short = ", ".join(c["name"] for c in summary[:6])
    if n > 6:
        city_list_short += f", and {n - 6} more"

    total_incidents = sum(c["row_count"] for c in summary)

    title = f"{SITE_NAME} — Free crime maps for {n} US cities"
    description = (
        f"Free interactive crime maps and incident tables for {n} major US cities "
        f"({city_list_short}). Fresh data from official police open-data portals, "
        f"updated regularly. See recent reported crime near you."
    )
    keywords = "crime map, crime map near me, city crime map, crime near me, neighborhood crime, police crime data, crime statistics, crime alerts"

    json_ld = [
        _org_ld(),
        _website_ld(),
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": f"Crime maps for {n} US cities",
            "itemListElement": [
                {
                    "@type": "ListItem",
                    "position": i + 1,
                    "url": f"{BASE_URL}/{c['slug']}",
                    "name": f"{c['name']}, {c['state_abbrev']} crime map",
                }
                for i, c in enumerate(summary)
            ],
        },
    ]

    html = head(title, description, f"{BASE_URL}/", keywords=keywords, json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(None, summary, static_active="home")
    html += f"""
<main class="max-w-7xl mx-auto px-4 py-10">
  <section class="text-center mb-10">
    <h1 class="text-4xl md:text-5xl font-bold tracking-tight mb-3">Crime maps for {n} US cities</h1>
    <p class="text-slate-600 max-w-2xl mx-auto text-lg">
      Interactive crime maps and incident tables for {n} major US cities —
      built from official police open-data portals. Currently tracking
      <span class="font-semibold text-slate-900">{total_incidents:,} recent reported incidents</span>.
      Want alerts for your address? <a href="https://spotcrime.com" target="_blank" rel="noopener" class="text-brand-700 font-semibold hover:underline">Sign up free at SpotCrime</a>.
    </p>
  </section>
  <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5" aria-label="Cities">
"""
    html += "\n".join(cards)
    html += f"""
  </section>

  <section class="mt-16 max-w-3xl mx-auto text-slate-700">
    <h2 class="text-2xl font-bold text-slate-900 mb-3">About {SITE_NAME}</h2>
    <p class="mb-3">
      {SITE_NAME} publishes free, mobile-friendly crime maps for major US cities
      using data pulled directly from each city's official open-data portal
      (Socrata, ArcGIS, or CKAN). No login. No paywall. No app install.
    </p>
    <p class="mb-3">
      Every incident on every map is a real, publicly reported crime record from
      the police department. We classify offenses into eight consistent
      categories — Shooting, Robbery, Assault, Burglary, Theft, Arson,
      Vandalism, and Arrest — so you can compare across cities.
    </p>
    <p class="mb-3">
      For a full explanation of where the data comes from, how often it updates,
      and how we classify offenses, see the <a href="/about" class="text-brand-700 hover:underline font-semibold">About page</a> and <a href="/faq" class="text-brand-700 hover:underline font-semibold">FAQ</a>.
    </p>
  </section>
</main>
"""
    html += alerts_cta("your city", "https://spotcrime.com")
    html += footer(summary[0]["generated_at"] if summary else "", n)
    return html


# ─── Per-city page ───────────────────────────────────────────────────────

def city_page(city: dict, summary: list[dict]) -> str:
    name = city["city"]
    slug = city["slug"]
    state = city["state_abbrev"]
    cats = city["category_counts"]
    name_state = _city_with_state(name, state)
    n_incidents = city["row_count"]
    window = city["window_days"]

    # Top category(ies) for a keyword-rich description
    top3 = list(cats.items())[:3]
    top3_str = ", ".join(f"{v:,} {k.lower()}" for k, v in top3) if top3 else ""

    title = f"{name_state} Crime Map — {n_incidents:,} Recent Incidents | {SITE_NAME}"
    description = (
        f"Interactive {name} crime map with {n_incidents:,} reported incidents from the last "
        f"{window} days: {top3_str}. Data sourced directly from {city['data_source']}. "
        f"Free crime alerts for {name}, {state}."
    )
    keywords = ", ".join([
        f"{name} crime map",
        f"{name} crime",
        f"crime in {name}",
        f"{name}, {state} crime",
        f"crime map {name}",
        f"crime near me {name}",
        f"{name} police reports",
        f"{name} crime rate",
    ])

    breadcrumbs = _breadcrumb_ld([
        ("Home", f"{BASE_URL}/"),
        ("Crime Maps", f"{BASE_URL}/"),
        (f"{name}, {state}", f"{BASE_URL}/{slug}"),
    ])

    json_ld = [
        _org_ld(),
        breadcrumbs,
        _dataset_ld(city),
    ]

    html = head(
        title,
        description,
        f"{BASE_URL}/{slug}",
        keywords=keywords,
        og_type="article",
        json_ld=json_ld,
    )
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(slug, summary)

    # Server-rendered preview (first 10 incidents) — visible until JS
    # populates the full interactive table.
    incidents = city.get("incidents", [])
    preview_rows = _incident_preview(incidents, limit=10)
    top_cat_name = top3[0][0] if top3 else "incidents"

    unlocated_note = ""
    if city.get("unlocated_count"):
        unlocated_note = (
            f"<p class='text-xs text-slate-500 mt-1'>{city.get('unlocated_count', 0):,} "
            "additional incidents could not be located on the map (address could not be geocoded).</p>"
        )

    html += f"""
<main class="max-w-7xl mx-auto px-4 py-8">
  <nav aria-label="Breadcrumb" class="text-xs text-slate-500 mb-3">
    <a href="/" class="hover:text-brand-700">Home</a> <span class="mx-1">›</span>
    <a href="/" class="hover:text-brand-700">Crime maps</a> <span class="mx-1">›</span>
    <span class="text-slate-700">{name_state}</span>
  </nav>

  <section class="mb-6">
    <h1 class="text-3xl md:text-4xl font-bold tracking-tight mb-1">{name_state} crime map</h1>
    <p class="text-slate-600">{n_incidents:,} recent incidents · last {window} days · source: <a href="{city['data_source_url']}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">{city['data_source']}</a></p>
    {unlocated_note}
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-3 mb-4">
    <div id="map" style="height: 520px;" class="rounded" aria-label="Interactive crime map of {name_state}"></div>
    <div class="mt-3">{legend(cats)}</div>
    <div id="hotspotInfo" class="mt-2 text-xs text-slate-500 hidden">
      <span class="inline-block w-3 h-3 align-middle mr-1" style="background:#dc2626;opacity:0.5;border:1px solid #7f1d1d;"></span>
      Predicted risk overlay: top 10% of grid cells by modelled risk. Toggle via the layers control on the map.
      <a href="#" id="hotspotHelp" class="text-brand-700 hover:underline">What is this?</a>
    </div>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-5 mb-8 text-slate-700 text-sm leading-relaxed">
    <h2 class="text-lg font-bold text-slate-900 mb-2">About the {name} crime map</h2>
    <p class="mb-2">
      This page shows <strong>{n_incidents:,} reported crime incidents in {name_state}</strong> from the last {window} days, aggregated directly from the
      <a href="{city['data_source_url']}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">{city['data_source']}</a>.
      The most common category in the current window is <strong>{top_cat_name}</strong>.
    </p>
    <p class="mb-2">
      Each dot on the map is a single reported incident. Click a dot for the date, offense description, and block-level address. Use the table below to filter by category or search by address.
    </p>
    <p class="text-xs text-slate-500">
      Open-data portals lag the real world by days to weeks. If you want faster notifications about crimes near a specific address in {name}, sign up for free daily email alerts on <a href="{city['spotcrime_alerts_url']}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">SpotCrime</a>.
    </p>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-4 mb-8">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
      <h2 class="text-lg font-bold">Recent {name} incidents</h2>
      <div class="flex flex-wrap gap-2 items-center">
        <label class="text-sm text-slate-600" for="catFilter">Filter:</label>
        <select id="catFilter" class="border border-slate-300 rounded px-2 py-1 text-sm">
          <option value="">All categories</option>
        </select>
        <input id="searchFilter" type="search" placeholder="Search address or offense…" class="border border-slate-300 rounded px-2 py-1 text-sm w-56" aria-label="Search incidents">
        <span id="rowCount" class="text-xs text-slate-500 font-mono"></span>
      </div>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-slate-100 text-slate-700">
          <tr>
            <th class="px-3 py-2 text-left">Date</th>
            <th class="px-3 py-2 text-left">Category</th>
            <th class="px-3 py-2 text-left">Offense</th>
            <th class="px-3 py-2 text-left">Address</th>
          </tr>
        </thead>
        <tbody id="incidentTable">
{preview_rows}
        </tbody>
      </table>
    </div>
    <div class="flex items-center justify-between mt-3 text-sm">
      <button id="prevPage" class="px-3 py-1 bg-slate-200 rounded disabled:opacity-50">← Prev</button>
      <span id="pageInfo" class="text-slate-600"></span>
      <button id="nextPage" class="px-3 py-1 bg-slate-200 rounded disabled:opacity-50">Next →</button>
    </div>
  </section>
</main>
"""
    html += alerts_cta(name, city["spotcrime_alerts_url"])
    html += footer(city["generated_at"], len(summary))

    # Page-specific JS
    cat_color_js = json.dumps(CATEGORY_COLORS)
    map_center_js = json.dumps(city["map_center"])
    map_zoom_js = city["map_zoom"]
    html += f"""
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(async function() {{
  const CAT_COLORS = {cat_color_js};
  const res = await fetch('/data/{slug}.json');
  const data = await res.json();
  const incidents = data.incidents;

  // ── Map ─────────────────────────────────────────────────────────────────
  const map = L.map('map').setView({map_center_js}, {map_zoom_js});
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }}).addTo(map);

  const incidentLayer = L.layerGroup();
  for (const inc of incidents) {{
    const color = CAT_COLORS[inc.category || 'Unclassified'] || '#64748b';
    const m = L.circleMarker([inc.lat, inc.lng], {{
      radius: 4, fillColor: color, color: color, weight: 1, opacity: 0.9, fillOpacity: 0.6,
    }});
    m.bindPopup(`<div class="text-sm">
      <div class="font-bold">${{inc.category || 'Unclassified'}}</div>
      <div>${{inc.description || ''}}</div>
      <div class="text-slate-600">${{inc.address || ''}}</div>
      <div class="text-slate-500 text-xs">${{inc.datetime ? new Date(inc.datetime).toLocaleString() : ''}}</div>
    </div>`);
    incidentLayer.addLayer(m);
  }}
  incidentLayer.addTo(map);

  // ── Predicted risk overlay (optional, per-city) ───────────────────
  try {{
    const hRes = await fetch('/data/{slug}_hotspots.geojson');
    if (hRes.ok) {{
      const hGeo = await hRes.json();
      function riskColor(r) {{
        if (r >= 0.85) return '#7f1d1d';
        if (r >= 0.65) return '#b91c1c';
        if (r >= 0.45) return '#dc2626';
        return '#f87171';
      }}
      const hotspotLayer = L.geoJSON(hGeo, {{
        style: (feature) => ({{
          fillColor: riskColor(feature.properties.risk),
          fillOpacity: 0.45,
          color: riskColor(feature.properties.risk),
          weight: 0.5,
          opacity: 0.8,
        }}),
        onEachFeature: (feature, layer) => {{
          const p = feature.properties;
          const rank = p.rank;
          const rankOf = p.rank_of;
          const rankStr = (rank && rankOf) ? `#${{rank}} of ${{rankOf}} hottest cells` : `Risk ${{(p.risk*100).toFixed(0)}}/100`;
          const predStr = (p.pred_count !== undefined)
            ? `Predicted incidents: ~${{p.pred_count.toFixed(1)}} per cell`
            : '';
          layer.bindPopup(
            `<div class="text-sm"><div class="font-bold">Predicted hot spot</div>` +
            `<div>${{rankStr}}</div>` +
            (predStr ? `<div class="text-slate-600">${{predStr}}</div>` : '') +
            `<div class="text-slate-500 text-xs mt-1">Random-forest model on ${{hGeo.properties.n_train || '?'}} training incidents</div></div>`
          );
        }},
      }});
      L.control.layers(null, {{
        'Incidents': incidentLayer,
        'Predicted risk': hotspotLayer,
      }}, {{ collapsed: false }}).addTo(map);
      hotspotLayer.addTo(map);
      document.getElementById('hotspotInfo').classList.remove('hidden');
      const help = document.getElementById('hotspotHelp');
      if (help) {{
        help.addEventListener('click', (e) => {{
          e.preventDefault();
          const pai = hGeo.properties.metrics && hGeo.properties.metrics.pai;
          const paiStr = pai ? `PAI = ${{pai.toFixed(2)}} (a random baseline is 1.0)` : 'Validation PAI not available.';
          alert(
            'The Predicted risk layer highlights grid cells the model rates as ' +
            'most likely to see incidents in the near future.\\n\\n' +
            'Method: random-forest regression on kernel density, XY, and ' +
            'lagged counts (Wheeler & Steenbeek 2021, "Mapping the Risk ' +
            'Terrain for Crime Using Machine Learning").\\n\\n' +
            paiStr + '\\n\\n' +
            'Grid: ' + (hGeo.properties.cell_size_m || '?') + 'm cells, ' +
            (hGeo.properties.n_cells_hot || 0) + ' shown.'
          );
        }});
      }}
    }}
  }} catch (e) {{ /* hotspots file not present for this city; ignore */ }}

  // ── Table ───────────────────────────────────────────────────────────────
  const PAGE_SIZE = 25;
  let filtered = incidents.slice();
  let page = 0;
  const catFilter = document.getElementById('catFilter');
  const searchFilter = document.getElementById('searchFilter');
  const tbody = document.getElementById('incidentTable');
  const rowCount = document.getElementById('rowCount');
  const pageInfo = document.getElementById('pageInfo');
  const prev = document.getElementById('prevPage');
  const next = document.getElementById('nextPage');

  const allCats = new Set(incidents.map(i => i.category || 'Unclassified'));
  for (const c of [...allCats].sort()) {{
    const opt = document.createElement('option'); opt.value = c; opt.textContent = c; catFilter.appendChild(opt);
  }}

  function applyFilters() {{
    const cat = catFilter.value;
    const q = searchFilter.value.toLowerCase().trim();
    filtered = incidents.filter(i => {{
      if (cat && (i.category || 'Unclassified') !== cat) return false;
      if (q) {{
        const hay = ((i.address || '') + ' ' + (i.description || '')).toLowerCase();
        if (!hay.includes(q)) return false;
      }}
      return true;
    }});
    page = 0;
    render();
  }}

  function render() {{
    const total = filtered.length;
    const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    page = Math.min(page, pages - 1);
    const slice = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
    tbody.innerHTML = slice.map(i => {{
      const color = CAT_COLORS[i.category || 'Unclassified'] || '#64748b';
      const dt = i.datetime ? new Date(i.datetime) : null;
      const dtStr = dt && !isNaN(dt) ? dt.toLocaleString([], {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }}) : '—';
      return `<tr class="border-b border-slate-100 hover:bg-slate-50">
        <td class="px-3 py-2 text-slate-700 whitespace-nowrap">${{dtStr}}</td>
        <td class="px-3 py-2"><span class="inline-flex items-center gap-1"><span class="legend-dot" style="background:${{color}}"></span>${{i.category || 'Unclassified'}}</span></td>
        <td class="px-3 py-2 text-slate-700">${{i.description || ''}}</td>
        <td class="px-3 py-2 text-slate-700">${{i.address || ''}}</td>
      </tr>`;
    }}).join('');
    rowCount.textContent = `${{total.toLocaleString()}} matching`;
    pageInfo.textContent = `Page ${{page + 1}} of ${{pages}}`;
    prev.disabled = page <= 0;
    next.disabled = page >= pages - 1;
  }}

  catFilter.addEventListener('change', applyFilters);
  searchFilter.addEventListener('input', applyFilters);
  prev.addEventListener('click', () => {{ page--; render(); }});
  next.addEventListener('click', () => {{ page++; render(); }});
  render();
}})();
</script>
"""
    return html


# ─── About / FAQ pages ────────────────────────────────────────────────────

def about_page(summary: list[dict]) -> str:
    n = len(summary)
    title = f"About {SITE_NAME} — Where the crime data comes from"
    description = (
        f"{SITE_NAME} publishes free crime maps for {n} US cities using data sourced directly "
        "from official police open-data portals. Learn where the data comes from, how often it "
        "updates, and how we classify offenses."
    )
    keywords = "about crime map, crime data source, police open data, crime data methodology, crime map how it works"
    json_ld = [_org_ld(), _breadcrumb_ld([
        ("Home", f"{BASE_URL}/"),
        ("About", f"{BASE_URL}/about"),
    ])]
    html = head(title, description, f"{BASE_URL}/about", keywords=keywords, json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(None, summary, static_active="about")

    city_source_rows = "\n".join(
        f'<tr class="border-b border-slate-100"><td class="px-3 py-2"><a class="text-brand-700 hover:underline" href="/{c["slug"]}">{c["name"]}, {c["state_abbrev"]}</a></td><td class="px-3 py-2 text-slate-600">Last {c["window_days"]} days · {c["row_count"]:,} incidents</td></tr>'
        for c in summary
    )

    html += f"""
<main class="max-w-4xl mx-auto px-4 py-10 text-slate-700 leading-relaxed">
  <h1 class="text-3xl md:text-4xl font-bold text-slate-900 mb-4">About {SITE_NAME}</h1>
  <p class="text-lg mb-6">
    {SITE_NAME} is a free, mobile-friendly crime-map site covering {n} major US cities.
    Every incident on every map is a real, publicly reported crime record from that city's
    police department — pulled directly from the city's official open-data portal.
  </p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">Where does the crime data come from?</h2>
  <p class="mb-3">
    We do not scrape. We do not buy data. We ingest each city's <strong>official open-data feed</strong>
    (Socrata, ArcGIS, or CKAN) and normalize the incident records into a consistent schema.
    That means the data you see on {SITE_NAME} is the same data the city publishes on its own portal —
    same fields, same coordinates, same block-level addresses — presented on an easier-to-use map.
  </p>
  <p class="mb-3">
    Under the hood, all of this runs on <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop" target="_blank" rel="noopener">tidycop</a>,
    a permissively-licensed open-source library. If you want to see exactly how a given city is
    ingested, the source code is public.
  </p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">Cities we currently cover</h2>
  <div class="overflow-x-auto">
    <table class="w-full text-sm">
      <thead class="bg-slate-100"><tr><th class="px-3 py-2 text-left">City</th><th class="px-3 py-2 text-left">Coverage</th></tr></thead>
      <tbody>
{city_source_rows}
      </tbody>
    </table>
  </div>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">How often does the data update?</h2>
  <p class="mb-3">
    Data is refreshed on a rolling basis from each city's open-data portal. City portals themselves
    vary — some publish incidents within 24 hours, others lag a week or more. Each city page shows
    the exact window of days being displayed. For real-time alerts about crimes near a specific
    address, we recommend <a class="text-brand-700 hover:underline" href="https://spotcrime.com" target="_blank" rel="noopener">SpotCrime</a>,
    which supports free daily email alerts nationwide.
  </p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">How do you classify offenses?</h2>
  <p class="mb-3">
    Every city defines its own offense codes, so a straight passthrough would make comparison across
    cities impossible. We normalize offenses into eight consistent categories:
  </p>
  <ul class="list-disc pl-6 mb-3 space-y-1">
    <li><strong>Shooting</strong> — firearm-related violent incidents (including fatal shootings).</li>
    <li><strong>Robbery</strong> — taking property from a person by force or threat.</li>
    <li><strong>Assault</strong> — attack on a person (including aggravated and simple assault).</li>
    <li><strong>Burglary</strong> — unlawful entry to commit theft or another felony.</li>
    <li><strong>Theft</strong> — non-violent taking of property (larceny, shoplifting, theft from vehicle).</li>
    <li><strong>Arson</strong> — intentional destruction of property by fire.</li>
    <li><strong>Vandalism</strong> — willful damage or defacement of property.</li>
    <li><strong>Arrest</strong> — an arrest event reported in the feed.</li>
  </ul>
  <p class="mb-3">
    Rows that don't map cleanly to one of these categories are labelled <em>Unclassified</em>. This
    matches the taxonomy used by the open-source
    <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop-spotcrime" target="_blank" rel="noopener">tidycop-spotcrime</a>
    classifier package.
  </p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">What about privacy?</h2>
  <p class="mb-3">
    We only display data the city itself has already published. Addresses are already generalized
    to the block level by the city before we ingest them. No victim or suspect identifying
    information is displayed.
  </p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">Who's behind this?</h2>
  <p class="mb-3">
    {SITE_NAME} is built and maintained on top of the open-source
    <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop" target="_blank" rel="noopener">tidycop</a> library
    by the SpotCrime team. Not affiliated with any law-enforcement agency.
  </p>

  <p class="mt-8"><a href="/" class="text-brand-700 hover:underline font-semibold">← Back to all city crime maps</a></p>
</main>
"""
    html += alerts_cta("your city", "https://spotcrime.com")
    html += footer(summary[0]["generated_at"] if summary else "", n)
    return html


FAQ_ITEMS = [
    ("Is CityCrimeMap free to use?",
     "Yes. Every map, every city, every incident. There is no paywall, no login, and no app to install. If you want free real-time email alerts for a specific address, sign up at SpotCrime."),
    ("Where does the crime data come from?",
     "Directly from each city's official open-data portal (typically Socrata, ArcGIS, or CKAN). We do not scrape. The dataset for every city is linked at the top of that city's page so you can verify."),
    ("How current is the data?",
     "It depends on the city. Some portals publish incidents within 24 hours; others lag a week or more. Each city page displays the exact window (\"last N days\") being shown. For faster notifications, use SpotCrime alerts."),
    ("Why don't you show every crime in my city?",
     "We only display what the city publishes. Some categories (like domestic violence and sex crimes involving minors) are intentionally excluded by the police department for victim privacy. That's a policy decision by the city, not by us."),
    ("Why is my neighborhood empty on the map?",
     "Two possibilities. First, no incidents were reported in that area during the current window — that's a good thing. Second, the incident was reported but the city couldn't geocode it (missing or bad address). We show a count of unlocated incidents on each city page when that happens."),
    ("How do you classify offenses across different cities?",
     "We normalize each city's offense codes into eight consistent categories: Shooting, Robbery, Assault, Burglary, Theft, Arson, Vandalism, and Arrest. Full definitions are on the About page. This lets you compare across cities apples-to-apples."),
    ("Can I get crime alerts for my address?",
     "Yes — through SpotCrime, which offers free daily email alerts for any US address nationwide. Every city page on CityCrimeMap has a direct sign-up link."),
    ("Do you cover the whole country?",
     "Not yet. We start with cities whose open-data feeds are current, populated, and have geocoded incidents. See the About page for the current list. New cities are added regularly. If your city isn't listed, SpotCrime covers thousands of US cities."),
    ("Do you sell my data or track me?",
     "No. We use Google Analytics for basic traffic reporting with anonymized IPs. We don't sell data, don't run ads, and don't have a login system that could collect PII."),
    ("Is this affiliated with any police department?",
     "No. CityCrimeMap is an independent public-interest project. We consume data that police departments have chosen to publish openly, but we're not affiliated with, endorsed by, or operated by any law-enforcement agency."),
    ("Can I embed one of these maps on my site?",
     "Not yet as a first-class embed, but every city page is public and shareable. Deep-link freely — the URLs are stable (e.g. citycrimemap.us/chicago). If you want a real embed or API, open an issue on the tidycop GitHub repo."),
    ("How is this different from CrimeMapping.com and Community Crime Map?",
     "Both of those are single-page apps whose content is mostly invisible to search engines and to screen readers. CityCrimeMap is fully static HTML — every city has its own crawlable page with real data. It's also open source, built on the free tidycop library, so anyone can inspect exactly how a city's data flows in."),
]


def faq_page(summary: list[dict]) -> str:
    n = len(summary)
    title = f"FAQ — {SITE_NAME}"
    description = (
        f"Answers to common questions about {SITE_NAME}: where the crime data comes from, "
        "how often it updates, how offenses are classified, and how to get free alerts."
    )
    keywords = "crime map FAQ, crime data questions, how does crime mapping work, crime map source"

    faq_ld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in FAQ_ITEMS
        ],
    }
    json_ld = [_org_ld(), _breadcrumb_ld([
        ("Home", f"{BASE_URL}/"),
        ("FAQ", f"{BASE_URL}/faq"),
    ]), faq_ld]

    html = head(title, description, f"{BASE_URL}/faq", keywords=keywords, json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(None, summary, static_active="faq")

    qa_html = ""
    for q, a in FAQ_ITEMS:
        qa_html += f"""
    <div class="mb-6">
      <h2 class="text-lg font-bold text-slate-900 mb-1">{q}</h2>
      <p class="text-slate-700">{a}</p>
    </div>"""

    html += f"""
<main class="max-w-4xl mx-auto px-4 py-10 text-slate-700 leading-relaxed">
  <h1 class="text-3xl md:text-4xl font-bold text-slate-900 mb-4">Frequently Asked Questions</h1>
  <p class="text-lg mb-8">Everything you might want to know about how {SITE_NAME} works, where the data comes from, and how to get more out of it.</p>

  {qa_html}

  <p class="mt-8"><a href="/" class="text-brand-700 hover:underline font-semibold">← Back to all city crime maps</a></p>
</main>
"""
    html += alerts_cta("your city", "https://spotcrime.com")
    html += footer(summary[0]["generated_at"] if summary else "", n)
    return html


# ─── robots.txt / sitemap.xml ────────────────────────────────────────────

def robots_txt() -> str:
    return f"""User-agent: *
Allow: /
Disallow: /data/

Sitemap: {BASE_URL}/sitemap.xml
"""


def sitemap_xml(summary: list[dict]) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries: list[str] = []

    def _entry(loc: str, priority: str, changefreq: str) -> str:
        return (
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority}</priority>\n"
            "  </url>"
        )

    entries.append(_entry(f"{BASE_URL}/", "1.0", "daily"))
    entries.append(_entry(f"{BASE_URL}/about", "0.6", "monthly"))
    entries.append(_entry(f"{BASE_URL}/faq", "0.6", "monthly"))
    for c in summary:
        entries.append(_entry(f"{BASE_URL}/{c['slug']}", "0.8", "daily"))
    body = "\n".join(entries)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{body}\n"
        "</urlset>\n"
    )


def favicon_svg() -> str:
    """Simple red-badge favicon — same brand color as the site header."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#b91c1c"/>'
        '<circle cx="32" cy="26" r="10" fill="none" stroke="white" stroke-width="4"/>'
        '<path d="M32 36 L32 52 M20 52 L44 52" stroke="white" stroke-width="4" stroke-linecap="round"/>'
        "</svg>"
    )


# ─── Main ────────────────────────────────────────────────────────────────

def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DATA_DIR.mkdir(parents=True, exist_ok=True)

    summary_path = DATA_DIR / "_summary.json"
    if not summary_path.exists():
        raise SystemExit("No _summary.json — run fetch_data.py first")
    summary = json.loads(summary_path.read_text())["cities"]

    # Per-city pages and bundled data
    for s in summary:
        slug = s["slug"]
        src = DATA_DIR / f"{slug}.json"
        if not src.exists():
            print(f"[gen] skip {slug}: no data file")
            continue
        shutil.copy(src, OUT_DATA_DIR / f"{slug}.json")
        hs_src = DATA_DIR / f"{slug}_hotspots.geojson"
        if hs_src.exists():
            shutil.copy(hs_src, OUT_DATA_DIR / f"{slug}_hotspots.geojson")
            print(f"[gen] copied {slug}_hotspots.geojson")
        full = json.loads(src.read_text())
        page_html = city_page(full, summary)
        (OUT_DIR / f"{slug}.html").write_text(page_html)
        print(f"[gen] wrote {slug}.html ({len(page_html):,} bytes)")

    # Index / About / FAQ
    (OUT_DIR / "index.html").write_text(index_page(summary))
    print("[gen] wrote index.html")
    (OUT_DIR / "about.html").write_text(about_page(summary))
    print("[gen] wrote about.html")
    (OUT_DIR / "faq.html").write_text(faq_page(summary))
    print("[gen] wrote faq.html")

    # SEO artefacts
    (OUT_DIR / "robots.txt").write_text(robots_txt())
    print("[gen] wrote robots.txt")
    (OUT_DIR / "sitemap.xml").write_text(sitemap_xml(summary))
    print("[gen] wrote sitemap.xml")
    (OUT_DIR / "favicon.svg").write_text(favicon_svg())
    print("[gen] wrote favicon.svg")

    # vercel.json — clean URLs + long-cache the /data/ JSON snapshots
    vercel_cfg = {
        "cleanUrls": True,
        "trailingSlash": False,
        "headers": [
            {
                "source": "/data/(.*).json",
                "headers": [
                    {"key": "Cache-Control", "value": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400"},
                    {"key": "Access-Control-Allow-Origin", "value": "*"},
                ],
            },
            {
                "source": "/(.*).html",
                "headers": [
                    {"key": "Cache-Control", "value": "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400"},
                ],
            },
        ],
    }
    (OUT_DIR / "vercel.json").write_text(json.dumps(vercel_cfg, indent=2))
    print("[gen] wrote vercel.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
