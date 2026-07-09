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
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from neighborhoods import (  # noqa: E402
    display_name as hood_display,
    hood_slug,
    group_incidents_by_hood,
    city_supports_hoods,
)

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "pages"
OUT_DATA_DIR = OUT_DIR / "data"

# Canonical domain for SEO (og:url, <link rel="canonical">).
# Override via env: BASE_URL=https://citymaps.vercel.app python generate_site.py
BASE_URL = os.environ.get("BASE_URL", "https://citycrimemap.us").rstrip("/")

# Google Analytics 4 measurement id. Defaults to the citycrimemap.us
# property (G-H7TPDESB8N, provisioned 2026-07-08). Override with GA4_ID=""
# to disable for local builds, or GA4_ID=G-OTHER to point at a different
# property.
GA4_ID = os.environ.get("GA4_ID", "G-H7TPDESB8N").strip()

# Google Search Console verification token (the value of the
# "content" attribute Google gives you for the meta-tag method).
GSC_VERIFICATION = os.environ.get("GSC_VERIFICATION", "").strip()

# Bing Webmaster Tools verification token (the value of the
# "content" attribute Bing gives you for the meta-tag method,
# a.k.a. msvalidate.01).
BING_VERIFICATION = os.environ.get("BING_VERIFICATION", "").strip()

# IndexNow key. Bing / Yandex / Seznam / Naver all accept IndexNow
# push notifications when we ship or update URLs. The key is public
# by design (it's served as a verification file at the domain root),
# so it's fine to hard-code. Regenerate with `openssl rand -hex 16`
# and drop a new <key>.txt at web/pages/ if it ever needs rotating.
INDEXNOW_KEY = "6797d8e9f1ba5116256e715981cb7802"

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


def _bing_meta() -> str:
    if not BING_VERIFICATION:
        return ""
    return f'\n  <meta name="msvalidate.01" content="{BING_VERIFICATION}">'


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
  <meta name="theme-color" content="#b91c1c">{_gsc_meta()}{_bing_meta()}
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
    a top-level static page ("home", "about", "faq", "predictions",
    "methodology", "near-me").

    Nav is trimmed to the top-level pages plus a "Cities ▾" dropdown
    so we don't ship a 20-item horizontal scroll on mobile.
    """
    def _cls(active: bool) -> str:
        return "font-bold text-white" if active else "text-brand-100/80 hover:text-brand-100"

    # Cities dropdown — active if a city page or the home page is active
    cities_active = active_slug is not None or static_active == "home"
    city_links = "".join(
        f'<a href="/{c["slug"]}" class="block px-3 py-1 text-sm text-slate-700 hover:bg-brand-50 hover:text-brand-800">{c["name"]}, {c["state_abbrev"]}</a>'
        for c in summary
    )

    top_items = f'''
      <a href="/" class="{_cls(static_active == "home")}">Home</a>
      <div class="relative group">
        <button type="button" class="{_cls(cities_active and static_active != "home")} inline-flex items-center gap-1" aria-haspopup="true">Cities <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clip-rule="evenodd"/></svg></button>
        <div class="absolute right-0 mt-2 w-56 bg-white rounded-lg shadow-lg ring-1 ring-black/5 py-2 hidden group-hover:block group-focus-within:block z-30 max-h-[70vh] overflow-y-auto">
          {city_links}
          <div class="border-t border-slate-100 mt-1 pt-1">
            <a href="/" class="block px-3 py-1 text-sm font-semibold text-brand-700 hover:bg-brand-50">All cities →</a>
          </div>
        </div>
      </div>
      <a href="/predictions" class="{_cls(static_active == "predictions")}">Predictions</a>
      <a href="/near-me" class="{_cls(static_active == "near-me")}">Crime near me</a>
      <a href="/methodology" class="{_cls(static_active == "methodology")}">Methodology</a>
      <a href="/about" class="{_cls(static_active == "about")}">About</a>
      <a href="/faq" class="{_cls(static_active == "faq")}">FAQ</a>
    '''
    return f"""
<header class="bg-brand-700 text-white">
  <div class="max-w-7xl mx-auto px-4 py-4 flex flex-wrap items-center justify-between gap-4">
    <a href="/" class="text-xl font-bold tracking-tight" aria-label="{SITE_NAME} home">🚨 {SITE_NAME}</a>
    <nav class="flex flex-wrap items-center gap-x-5 gap-y-1 text-sm" aria-label="Primary">
      {top_items}
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

    title = f"{SITE_NAME} — Predictive crime maps for {n} US cities"
    description = (
        f"{SITE_NAME} publishes free crime maps and machine-learning-based predicted risk "
        f"overlays for {n} US cities ({city_list_short}). Fresh data from official police "
        f"open-data portals + a peer-reviewed predictive model. Open source. Honest numbers."
    )
    keywords = (
        "crime map, crime near me, crime map near me, city crime map, predictive crime map, "
        "crime prediction, AI crime map, crime forecast, neighborhood crime, police crime data, "
        "crime statistics, crime alerts, crime hot spots"
    )

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
    <p class="uppercase tracking-widest text-xs text-brand-700 font-semibold mb-2">Crime maps + predictive risk</p>
    <h1 class="text-4xl md:text-5xl font-bold tracking-tight text-slate-900 mb-3">Where is crime happening — and where is it going next?</h1>
    <p class="text-slate-600 max-w-3xl mx-auto text-lg mb-5">
      {SITE_NAME} publishes free crime maps for {n} US cities <em>plus</em> a peer-reviewed
      machine-learning <a href="/predictions" class="text-brand-700 font-semibold hover:underline">predicted-risk overlay</a>
      — currently tracking <span class="font-semibold text-slate-900">{total_incidents:,} recent reported incidents</span>.
      All open source. No login, no paywall, no app.
    </p>
    <div class="flex flex-wrap justify-center gap-3">
      <a href="/near-me" class="inline-flex items-center gap-2 bg-brand-700 text-white px-5 py-2 rounded-lg font-bold hover:bg-brand-800 transition">📍 Crime near me</a>
      <a href="/predictions" class="inline-flex items-center gap-2 bg-white border border-slate-300 text-slate-800 px-5 py-2 rounded-lg font-bold hover:bg-slate-50 transition">How predictions work</a>
    </div>
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

def _city_prose_section(city, name, name_state, n_incidents, window, top_cat_name) -> str:
    """Rich per-city prose section shown between map and table.

    Includes: (1) methodology-honest data paragraph, (2) predicted-risk
    call-out with per-city PAI, (3) top-neighborhoods grid (when hoods
    are available), (4) category quick-links.
    """
    slug = city["slug"]
    incidents = city.get("incidents", [])
    cats = city["category_counts"]

    # PAI block
    meta = _load_hotspot_meta(slug)
    pai_block = ""
    if meta:
        metrics = meta.get("metrics") or {}
        pai = metrics.get("pai")
        n_cells = meta.get("n_cells_hot")
        cell_size = meta.get("cell_size_m")
        if pai is not None:
            verdict = _pai_verdict(pai)
            pct = int(pai * 10)
            pai_block = (
                f'<div class="bg-brand-50 border border-brand-100 rounded-lg p-4 mb-4">'
                f'<p class="text-xs uppercase tracking-widest font-semibold text-brand-700 mb-1">Predicted risk in {name}</p>'
                f'<p class="text-slate-800 mb-1">The map above includes a machine-learning-based <a href="/predictions" class="text-brand-700 font-semibold hover:underline">predicted-risk overlay</a> — the {n_cells or "top"} highest-risk {cell_size or 300} m cells across {name}. In the held-out test window, those cells captured roughly <strong>{pct}% of reported incidents</strong> (PAI = {pai:.2f} vs. 1.0 random baseline — a {verdict}).</p>'
                f'<p class="text-xs text-slate-600">Toggle the <em>Predicted risk</em> layer on the map to see the cells. <a href="/methodology" class="text-brand-700 hover:underline">Read the full methodology →</a></p>'
                f'</div>'
            )

    # Top neighborhoods (only when hoods are available)
    hoods_block = ""
    if city_supports_hoods(slug):
        groups = group_incidents_by_hood(slug, incidents)
        if groups:
            top_hoods = sorted(groups.items(), key=lambda kv: -kv[1]["count"])[:10]
            hood_cards = "".join(
                f'<a href="/{slug}/{g["slug"]}" class="block bg-slate-50 hover:bg-brand-50 border border-slate-200 hover:border-brand-500 rounded-lg px-3 py-2 transition">'
                f'<div class="font-semibold text-slate-800 text-sm">{hname}</div>'
                f'<div class="text-xs text-slate-500 font-mono">{g["count"]:,} incidents</div>'
                f'</a>'
                for hname, g in top_hoods
            )
            hoods_block = (
                f'<div class="mb-4">'
                f'<h3 class="font-bold text-slate-900 mb-2">Top {name} neighborhoods this window</h3>'
                f'<div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">{hood_cards}</div>'
                f'</div>'
            )

    # Category quick-links (skip Unclassified)
    cat_links = "".join(
        f'<a href="/{slug}/{cat.lower()}" class="inline-block bg-slate-100 hover:bg-brand-50 hover:text-brand-800 text-slate-700 rounded px-3 py-1 text-sm mr-2 mb-2">'
        f'{cat} <span class="text-xs text-slate-500">({cnt})</span></a>'
        for cat, cnt in cats.items() if cat != "Unclassified" and cnt >= 3
    )
    cat_block = ""
    if cat_links:
        cat_block = (
            f'<div class="mb-2">'
            f'<h3 class="font-bold text-slate-900 mb-2">Browse by category</h3>'
            f'<div>{cat_links}</div>'
            f'</div>'
        )

    return (
        f'<section class="bg-white border border-slate-200 rounded-lg p-5 mb-8 text-slate-700 text-sm leading-relaxed">'
        f'{pai_block}'
        f'{hoods_block}'
        f'{cat_block}'
        f'<h3 class="font-bold text-slate-900 mb-2">About this data</h3>'
        f'<p class="mb-2">This page shows <strong>{n_incidents:,} reported crime incidents in {name_state}</strong> from the last {window} days, aggregated directly from the <a href="{city["data_source_url"]}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">{city["data_source"]}</a>. The most common category in the current window is <strong>{top_cat_name}</strong>. Each dot on the map is a single reported incident; click any dot for date, offense description, and block-level address.</p>'
        f'<p class="text-xs text-slate-500">Open-data portals lag the real world by days to weeks. For real-time notifications when new crime is reported near a specific address in {name}, sign up for free daily email alerts on <a href="{city["spotcrime_alerts_url"]}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">SpotCrime</a>.</p>'
        f'</section>'
    )


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

  {_city_prose_section(city, name, name_state, n_incidents, window, top_cat_name)}

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


# ─── Predictions helper ─────────────────────────────────────────────────
def _load_hotspot_meta(slug: str) -> dict | None:
    p = DATA_DIR / f"{slug}_hotspots.geojson"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text())
        return d.get("properties") or None
    except Exception:
        return None


def _pai_verdict(pai: float | None) -> str:
    if pai is None:
        return "model not trained"
    if pai < 1.0:
        return "below random baseline (insufficient training data)"
    if pai < 1.5:
        return "modest lift over random"
    if pai < 2.5:
        return "strong lift"
    if pai < 4.0:
        return "very strong lift"
    return "excellent lift"


# ─── Predictions page ───────────────────────────────────────────────────
def predictions_page(summary: list[dict]) -> str:
    n = len(summary)
    rows = []
    for c in summary:
        meta = _load_hotspot_meta(c["slug"])
        pai = n_train = cells_hot = cell_size = None
        if meta:
            metrics = meta.get("metrics") or {}
            pai = metrics.get("pai")
            n_train = meta.get("n_train")
            cells_hot = meta.get("n_cells_hot")
            cell_size = meta.get("cell_size_m")
        rows.append({
            "slug": c["slug"], "name": c["name"], "state": c["state_abbrev"],
            "pai": pai, "n_train": n_train, "cells_hot": cells_hot,
            "cell_size": cell_size, "row_count": c["row_count"],
        })
    rows.sort(key=lambda r: (r["pai"] is None, -(r["pai"] or 0)))
    best = next((r for r in rows if r["pai"] is not None), None)
    best_line = ""
    if best:
        best_line = (
            f"On <a href='/{best['slug']}' class='underline hover:no-underline'>{best['name']}</a> "
            f"the model's top 10% of city cells captures roughly {int((best['pai'] or 0) * 10)}% of "
            f"reported incidents — a PAI of {best['pai']:.2f} against a random baseline of 1.0."
        )

    table_rows = []
    for r in rows:
        if r["pai"] is None:
            table_rows.append(
                f"<tr class='border-b border-slate-100'>"
                f"<td class='px-3 py-2'><a class='text-brand-700 hover:underline' href='/{r['slug']}'>{r['name']}, {r['state']}</a></td>"
                f"<td class='px-3 py-2 text-slate-500' colspan='4'>Predictive layer not enabled for this city yet.</td>"
                f"</tr>"
            )
            continue
        pai = r["pai"] or 0
        verdict = _pai_verdict(pai)
        table_rows.append(
            f"<tr class='border-b border-slate-100'>"
            f"<td class='px-3 py-2'><a class='text-brand-700 hover:underline font-semibold' href='/{r['slug']}'>{r['name']}, {r['state']}</a></td>"
            f"<td class='px-3 py-2 font-mono text-slate-900'>{pai:.2f}</td>"
            f"<td class='px-3 py-2 text-slate-600 text-sm'>{verdict}</td>"
            f"<td class='px-3 py-2 text-slate-500 text-sm font-mono'>{r['n_train'] or '—'} rows</td>"
            f"<td class='px-3 py-2 text-slate-500 text-sm font-mono'>{r['cells_hot'] or '—'} cells · {r['cell_size'] or '—'} m</td>"
            f"</tr>"
        )

    title = f"Predictive crime maps for {n} US cities — how it works | {SITE_NAME}"
    description = (
        f"{SITE_NAME} publishes machine-learning-based predicted crime risk overlays "
        f"for {n} US cities using peer-reviewed Wheeler & Steenbeek (2021) methodology. "
        "Random-forest models on 200-300m grids, kernel density features, validated with PAI. "
        "Open source, honest numbers."
    )
    keywords = (
        "crime prediction, predictive crime map, AI crime map, crime forecast, "
        "crime prediction near me, machine learning crime, hot spot prediction, "
        "risk terrain modeling, PAI predictive accuracy, random forest crime"
    )
    json_ld = [
        _org_ld(),
        _breadcrumb_ld([("Home", f"{BASE_URL}/"), ("Predictions", f"{BASE_URL}/predictions")]),
        {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": "How CityCrimeMap predicts crime hot spots",
            "description": description,
            "url": f"{BASE_URL}/predictions",
            "author": _org_ld(),
            "publisher": _org_ld(),
            "about": ["predictive crime mapping", "risk terrain modeling", "random forest", "kernel density estimation"],
            "citation": "Wheeler, A.P. & Steenbeek, W. (2021). Mapping the Risk Terrain for Crime Using Machine Learning. J Quant Criminol 37, 445–480. https://doi.org/10.1007/s10940-020-09457-7",
        },
    ]

    html = head(title, description, f"{BASE_URL}/predictions", keywords=keywords, json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(None, summary, static_active="predictions")

    city_cards = "".join(
        f'<a href="/{c["slug"]}" class="block bg-white border border-slate-200 rounded-lg p-4 hover:shadow-md hover:border-brand-500 transition">'
        f'<div class="flex items-baseline justify-between"><span class="font-bold text-slate-900">{c["name"]}, {c["state_abbrev"]}</span>'
        f'<span class="text-xs text-slate-500 font-mono">{c["row_count"]:,} recent</span></div>'
        f'<p class="text-xs text-brand-700 mt-1">See predicted risk →</p></a>'
        for c in summary
    )

    html += f"""
<main class="max-w-5xl mx-auto px-4 py-10 text-slate-700 leading-relaxed">
  <nav aria-label="Breadcrumb" class="text-xs text-slate-500 mb-3"><a href="/" class="hover:text-brand-700">Home</a> <span class="mx-1">›</span> <span class="text-slate-700">Predictions</span></nav>

  <section class="mb-10">
    <p class="uppercase tracking-widest text-xs text-brand-700 font-semibold mb-2">Predictive layer</p>
    <h1 class="text-4xl md:text-5xl font-bold tracking-tight text-slate-900 mb-4">Where is crime likely to happen next?</h1>
    <p class="text-xl text-slate-600 mb-4">{SITE_NAME} publishes a machine-learning-based <strong>predicted risk overlay</strong> on every city map. It highlights the small share of city blocks where reported incidents are most likely to concentrate in the near future.</p>
    <p class="text-slate-600">{best_line}</p>
    <div class="mt-6 flex gap-3">
      <a href="/methodology" class="inline-flex items-center gap-1 text-brand-700 font-semibold hover:underline">Full methodology →</a>
      <a href="https://github.com/colinmac-boop/tidycop-hotspots" target="_blank" rel="noopener" class="inline-flex items-center gap-1 text-slate-600 hover:text-brand-700">Source code (MIT) ↗</a>
    </div>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-6 mb-10">
    <h2 class="text-2xl font-bold text-slate-900 mb-4">How the model works</h2>
    <ol class="list-decimal pl-6 space-y-3 text-slate-700">
      <li><strong>Grid the city into small square cells.</strong> For dense cities we use 300 m cells; for smaller cities 200–250 m so the map has visible contrast. A typical US city ends up with somewhere between 5,000 and 15,000 grid cells.</li>
      <li><strong>Compute a smoothed density of past incidents per cell.</strong> This is a kernel density estimate (KDE) — a standard statistical technique for turning a scatter of points into a continuous surface. We rescale it (log-transform, normalize) so the machine-learning model can actually learn from it.</li>
      <li><strong>Train a random forest model</strong> to predict the incident count per cell in a held-out future window, using the KDE feature plus each cell's coordinates and lagged counts. Random forests are ensemble models built from hundreds of decision trees; they're a well-established baseline for spatial prediction because they handle non-linearities and sparse features gracefully.</li>
      <li><strong>Show only the top 10% of cells</strong> by predicted risk. Cells with zero predicted risk are dropped entirely so the GeoJSON payload stays small.</li>
    </ol>
    <p class="text-sm text-slate-500 mt-4">The methodology is a machine-learning adaptation of Risk Terrain Modeling, published in Wheeler &amp; Steenbeek (2021), <a href="https://doi.org/10.1007/s10940-020-09457-7" target="_blank" rel="noopener" class="text-brand-700 hover:underline">Journal of Quantitative Criminology</a>. Our full implementation is open source at <a href="https://github.com/colinmac-boop/tidycop-hotspots" target="_blank" rel="noopener" class="text-brand-700 hover:underline">tidycop-hotspots</a> (MIT).</p>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-6 mb-10">
    <h2 class="text-2xl font-bold text-slate-900 mb-3">What the numbers mean</h2>
    <p class="mb-4">We publish the <strong>Predictive Accuracy Index (PAI)</strong> for every city we cover. PAI = (share of incidents captured) ÷ (share of area used). A PAI of 1.0 means the model is no better than picking cells at random; 2.0 means it's twice as good; 3.0+ is a strong lift. It's the standard metric in the predictive-policing academic literature.</p>
    <p class="mb-4 text-slate-600 text-sm">Concretely, if the top 10% of San Francisco cells has a PAI of 4.6, that means those cells together contain about 46% of the reported incidents in the held-out test window — almost 5× what you'd get by guessing.</p>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-slate-100 text-slate-700"><tr><th class="px-3 py-2 text-left">City</th><th class="px-3 py-2 text-left">PAI @ 10%</th><th class="px-3 py-2 text-left">Verdict</th><th class="px-3 py-2 text-left">Train set</th><th class="px-3 py-2 text-left">Grid</th></tr></thead>
        <tbody>{''.join(table_rows)}</tbody>
      </table>
    </div>
    <p class="text-xs text-slate-500 mt-3">Sorted by PAI, best model first. Training sets are short right now (a few hundred rows per city) because we're only ingesting the last ~45 days. Longer training histories are on the roadmap and will improve every one of these numbers.</p>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-6 mb-10">
    <h2 class="text-2xl font-bold text-slate-900 mb-3">What the model does not do</h2>
    <p class="mb-3">We're deliberately narrow about what the predictive layer is for. It's a research-backed tool for public awareness, not a policing product.</p>
    <ul class="list-disc pl-6 space-y-2 text-slate-700">
      <li><strong>It predicts places, not people.</strong> The model outputs a risk score for a 300-meter grid cell. It does not identify individuals, license plates, faces, or any person-level attribute. Predictive policing systems that target individuals have a troubling accuracy and civil-liberties record; we don't build those.</li>
      <li><strong>It inherits the biases of the underlying data.</strong> Reported crime data reflects both real crime and where policing looks. Neighborhoods with more police presence tend to have more reported incidents even at the same true crime rate. The risk overlay inherits that bias. We flag it explicitly instead of hiding it.</li>
      <li><strong>It's not real-time.</strong> The city portals we ingest lag the real world by days to weeks. If you want notifications about crimes reported near a specific address right now, use <a href="https://spotcrime.com" target="_blank" rel="noopener" class="text-brand-700 hover:underline">SpotCrime</a>'s free daily email alerts.</li>
      <li><strong>Short training windows produce noisy models.</strong> Cities with sparse data score close to — or below — the random baseline right now. That's honest: with 200 rows to train on, you can't learn much.</li>
    </ul>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-6 mb-10">
    <h2 class="text-2xl font-bold text-slate-900 mb-3">Compared to other crime maps</h2>
    <p class="mb-3">Most public crime maps show only historical dots. That's useful for a look-back but doesn't tell you where risk concentrates going forward. To our knowledge, {SITE_NAME} is the only free, open-source, city-agnostic crime map that ships a peer-reviewed predictive layer.</p>
    <ul class="list-disc pl-6 space-y-2 text-slate-700">
      <li><strong>Community Crime Map (LexisNexis):</strong> historical dots only. No forecasting.</li>
      <li><strong>CrimeMapping.com:</strong> historical dots only. No forecasting.</li>
      <li><strong>Nextdoor:</strong> user-reported anecdotes. No data model, no verification.</li>
      <li><strong>SpotCrime:</strong> best-in-class historical maps and free alerts. No public predictive layer.</li>
      <li><strong>{SITE_NAME}:</strong> historical map + predicted-risk overlay + open-source methodology + honest validation metrics.</li>
    </ul>
  </section>

  <section class="mb-10">
    <h2 class="text-2xl font-bold text-slate-900 mb-4">See predictions for your city</h2>
    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">{city_cards}</div>
  </section>

  <p class="mt-10 text-slate-500 text-sm">Have questions about the model? Read the <a class="text-brand-700 hover:underline" href="/methodology">full methodology page</a>, the <a class="text-brand-700 hover:underline" href="/faq">FAQ</a>, or file an issue on <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop-hotspots" target="_blank" rel="noopener">GitHub</a>.</p>
</main>
"""
    html += alerts_cta("your city", "https://spotcrime.com")
    html += footer(summary[0]["generated_at"] if summary else "", n)
    return html


# ─── Methodology page ───────────────────────────────────────────────────
def methodology_page(summary: list[dict]) -> str:
    n = len(summary)
    title = f"Methodology — how {SITE_NAME} works | Predictive crime modeling, open source"
    description = (
        f"Full technical methodology for {SITE_NAME}: how we ingest data from {n} US city "
        "open-data portals, how the SpotCrime 8-category classifier normalizes offenses, "
        "and how the random-forest predictive model is trained and validated (Wheeler & "
        "Steenbeek 2021 RTM methodology)."
    )
    keywords = "crime map methodology, predictive crime modeling, risk terrain modeling, random forest crime prediction, PAI predictive accuracy index, Wheeler Steenbeek crime, kernel density crime, open source crime data"
    json_ld = [
        _org_ld(),
        _breadcrumb_ld([("Home", f"{BASE_URL}/"), ("Methodology", f"{BASE_URL}/methodology")]),
        {
            "@context": "https://schema.org",
            "@type": "TechArticle",
            "headline": "CityCrimeMap Methodology",
            "description": description,
            "url": f"{BASE_URL}/methodology",
            "publisher": _org_ld(),
            "citation": "Wheeler, A.P. & Steenbeek, W. (2021). Mapping the Risk Terrain for Crime Using Machine Learning. J Quant Criminol 37, 445–480. https://doi.org/10.1007/s10940-020-09457-7",
        },
    ]
    html = head(title, description, f"{BASE_URL}/methodology", keywords=keywords, json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(None, summary, static_active="methodology")
    html += f"""
<main class="max-w-4xl mx-auto px-4 py-10 text-slate-700 leading-relaxed">
  <nav aria-label="Breadcrumb" class="text-xs text-slate-500 mb-3"><a href="/" class="hover:text-brand-700">Home</a> <span class="mx-1">›</span> <span class="text-slate-700">Methodology</span></nav>
  <h1 class="text-3xl md:text-4xl font-bold text-slate-900 mb-3">Methodology</h1>
  <p class="text-lg text-slate-600 mb-8">How {SITE_NAME} ingests, normalizes, classifies, and models crime data for {n} US cities. Every step below is implemented in publicly readable Python. Nothing is proprietary.</p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">1. Data ingest</h2>
  <p class="mb-3">We consume each city's official open-data portal directly. The three portal families we support cover roughly 95% of US cities that publish crime data at all:</p>
  <ul class="list-disc pl-6 space-y-1 mb-3">
    <li><strong>Socrata</strong> (Chicago, Seattle, San Francisco, Cincinnati, Cleveland, Detroit, Denver, Minneapolis, Rochester, and others)</li>
    <li><strong>ArcGIS FeatureServer / MapServer</strong> (Washington DC, Houston, Pittsburgh, Indianapolis, Boston, Hartford, Gainesville, and others)</li>
    <li><strong>CKAN</strong> (fallback for a handful of smaller cities)</li>
  </ul>
  <p class="mb-3">Ingest is handled by the open-source <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop" target="_blank" rel="noopener">tidycop</a> library (MIT), a Python port of Anthony Galvan's R <a class="text-brand-700 hover:underline" href="https://github.com/Steal-This-Code/tidycops" target="_blank" rel="noopener">tidycops</a> package. We add nothing over the wire that the city hasn't already published; we simply pull, normalize, and cache. The registry that defines each city's field mapping is <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop/blob/main/registry/cities.yaml" target="_blank" rel="noopener">a single YAML file</a> you can inspect.</p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">2. Offense classification</h2>
  <p class="mb-3">Every city defines its own offense codes — NIBRS, UCR variants, custom vocabularies, or plain-English descriptions. Direct passthrough would make cross-city comparison impossible. We normalize into <strong>eight categories</strong>:</p>
  <div class="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3 text-sm">
    <div class="bg-slate-100 rounded px-3 py-2"><strong>Shooting</strong></div><div class="bg-slate-100 rounded px-3 py-2"><strong>Robbery</strong></div>
    <div class="bg-slate-100 rounded px-3 py-2"><strong>Assault</strong></div><div class="bg-slate-100 rounded px-3 py-2"><strong>Burglary</strong></div>
    <div class="bg-slate-100 rounded px-3 py-2"><strong>Theft</strong></div><div class="bg-slate-100 rounded px-3 py-2"><strong>Arson</strong></div>
    <div class="bg-slate-100 rounded px-3 py-2"><strong>Vandalism</strong></div><div class="bg-slate-100 rounded px-3 py-2"><strong>Arrest</strong></div>
  </div>
  <p class="mb-3">Classification uses the open-source <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop-spotcrime" target="_blank" rel="noopener">tidycop-spotcrime</a> package. Rows that don't map cleanly are labelled <em>Unclassified</em> rather than force-fit into a bucket. Coverage varies by city; see each city's page for the current breakdown.</p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">3. Geocoding (where needed)</h2>
  <p class="mb-3">Most feeds publish latitude/longitude. When a city publishes addresses but no coordinates (currently: Boston), we resolve them via the <a class="text-brand-700 hover:underline" href="https://geocoding.geo.census.gov/geocoder/" target="_blank" rel="noopener">U.S. Census Bureau batch geocoder</a>, with a SQLite cache to avoid re-hitting the API. Unmatched rows are counted honestly as "N incidents could not be located" beneath the map.</p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">4. Predictive risk model</h2>
  <p class="mb-3">The predicted-risk overlay is generated by <a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop-hotspots" target="_blank" rel="noopener">tidycop-hotspots</a>, a pure-Python implementation of the machine-learning Risk Terrain Modeling methodology published by Wheeler and Steenbeek in the <a class="text-brand-700 hover:underline" href="https://doi.org/10.1007/s10940-020-09457-7" target="_blank" rel="noopener">Journal of Quantitative Criminology</a> (2021). No ArcGIS Pro license required. The implementation is MIT-licensed and readable.</p>

  <h3 class="text-lg font-bold text-slate-900 mt-4 mb-2">Grid</h3>
  <p class="mb-3">Cities are gridded into square cells of 200–300 meters depending on incident density. Denser cities get larger cells so cell counts stay uniformly-distributed enough for training; smaller cities get tighter cells so the map has visible contrast. Hex grids are also supported upstream and are a possible future refinement.</p>

  <h3 class="text-lg font-bold text-slate-900 mt-4 mb-2">Features</h3>
  <ul class="list-disc pl-6 space-y-1 mb-3">
    <li><strong>Kernel density estimate</strong> of prior incidents at each cell centroid, with a Gaussian kernel and bandwidth of 350–500 m depending on city size. Values are log-transformed (log1p of the normalized density) before being fed to the model, because raw KDE values on city-scale grids sit in the 1e-10 range and cause the RF to learn a constant.</li>
    <li><strong>Cell centroid X/Y coordinates</strong> for spatial context.</li>
    <li><strong>Lagged incident counts</strong> per cell from the training window.</li>
  </ul>

  <h3 class="text-lg font-bold text-slate-900 mt-4 mb-2">Model</h3>
  <p class="mb-3"><code class="bg-slate-100 px-1 rounded">sklearn.ensemble.RandomForestRegressor</code> with <code>n_estimators=400</code>, <code>min_samples_leaf=5</code>. Random forests are the baseline model in the Wheeler &amp; Steenbeek paper and continue to perform competitively with gradient-boosted trees at this problem scale, with a fraction of the tuning burden.</p>

  <h3 class="text-lg font-bold text-slate-900 mt-4 mb-2">Training / test split</h3>
  <p class="mb-3">We split by <strong>time</strong>, not by row — the first ≈65% of the window is training, the last ≈35% is held-out test. This is the leakage-free protocol Wheeler &amp; Steenbeek recommend. Fitting the KDE feature on the training window only is important; refitting on the whole window would leak test-window information into the feature vector.</p>

  <h3 class="text-lg font-bold text-slate-900 mt-4 mb-2">Inference</h3>
  <p class="mb-3">We deliberately do inference twice. The fitted tree is applied first to the training-window KDE to compute the honest test-set PAI. It is applied a second time to a KDE built from the full window, and that surface is what we ship on the map — so the user sees where things are hot <em>right now</em>, not where they were hot last month. The fitted decision function is the same both times; only the input feature vector changes.</p>

  <h3 class="text-lg font-bold text-slate-900 mt-4 mb-2">Output</h3>
  <p class="mb-3">We keep only the top 10% of positive-risk cells and drop the rest, which shrinks the payload from ≈15,000 cells to a few dozen. Each output cell carries <code>risk</code> (0–1), <code>rank</code> / <code>rank_of</code> for ordering, and <code>pred_count</code> — the raw predicted incident count per cell over the training-window duration.</p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">5. Validation — Predictive Accuracy Index (PAI)</h2>
  <p class="mb-3">Every model is validated with the <strong>Predictive Accuracy Index</strong>:</p>
  <p class="mb-3 bg-slate-100 rounded p-3 font-mono text-sm text-slate-800">PAI = (incidents in flagged cells / total incidents) &divide; (flagged cell area / total area)</p>
  <p class="mb-3">A PAI of 1.0 is random. 2.0 is twice as good as random; 4.0 is four times. We report PAI at 10% of the area (the standard reporting convention in the RTM literature) for every city. See the <a class="text-brand-700 hover:underline" href="/predictions">predictions page</a> for the current per-city numbers.</p>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">6. Bias and limitations</h2>
  <p class="mb-3">Reported crime data does not equal real crime. It reflects both criminal activity and where policing looks. Predictive models built on that data inherit both. We flag this explicitly rather than pretend otherwise:</p>
  <ul class="list-disc pl-6 space-y-1 mb-3">
    <li>The risk overlay is <strong>place-based</strong>, not person-based. We do not model or predict individuals.</li>
    <li>The overlay is <strong>advisory</strong>, not decisional. It is not a policing product and does not recommend deployment.</li>
    <li>Cities with sparse training data produce noisy models; some score at or below the random baseline. We publish those numbers alongside the good ones.</li>
  </ul>

  <h2 class="text-2xl font-bold text-slate-900 mt-8 mb-3">7. Reproducibility</h2>
  <p class="mb-3">Everything on this site is reproducible from three open-source Python packages:</p>
  <ul class="list-disc pl-6 space-y-1 mb-3">
    <li><a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop" target="_blank" rel="noopener">tidycop</a> — city-agnostic data ingest</li>
    <li><a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop-spotcrime" target="_blank" rel="noopener">tidycop-spotcrime</a> — offense classifier</li>
    <li><a class="text-brand-700 hover:underline" href="https://github.com/colinmac-boop/tidycop-hotspots" target="_blank" rel="noopener">tidycop-hotspots</a> — predictive model</li>
  </ul>
  <p class="mb-3">All MIT licensed. Clone the repo, install the packages, and you can regenerate every map on this site.</p>

  <p class="mt-8"><a href="/predictions" class="text-brand-700 hover:underline font-semibold">← Back to predictions overview</a></p>
</main>
"""
    html += alerts_cta("your city", "https://spotcrime.com")
    html += footer(summary[0]["generated_at"] if summary else "", n)
    return html


# ─── /near-me router ────────────────────────────────────────────────────
def near_me_page(summary: list[dict]) -> str:
    n = len(summary)
    title = f"Crime near me — find your city's crime map | {SITE_NAME}"
    description = (
        f"Find crime maps and predicted crime risk near you. {SITE_NAME} covers {n} US cities "
        "with interactive maps, incident tables, and machine-learning-based predictive overlays."
    )
    keywords = "crime near me, crime map near me, crime in my area, local crime map, neighborhood crime, safety near me, crime by zip code, crime by address"
    json_ld = [_org_ld(), _breadcrumb_ld([("Home", f"{BASE_URL}/"), ("Crime near me", f"{BASE_URL}/near-me")])]
    html = head(title, description, f"{BASE_URL}/near-me", keywords=keywords, json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(None, summary, static_active="near-me")

    picker = "".join(
        f'<a href="/{c["slug"]}" class="block bg-white border border-slate-200 rounded-lg p-4 hover:shadow-md hover:border-brand-500 transition">'
        f'<div class="font-bold text-slate-900">{c["name"]}, {c["state_abbrev"]}</div>'
        f'<p class="text-xs text-slate-500 mt-1">{c["row_count"]:,} recent incidents</p>'
        f'<p class="text-xs text-brand-700 mt-2">Open crime map →</p></a>'
        for c in summary
    )

    city_coords = []
    for c in summary:
        p = DATA_DIR / f"{c['slug']}.json"
        if p.exists():
            try:
                d = json.loads(p.read_text())
                mc = d.get("map_center") or [None, None]
                if mc[0] is not None:
                    city_coords.append({"slug": c["slug"], "name": c["name"], "state": c["state_abbrev"], "lat": mc[0], "lng": mc[1]})
            except Exception:
                pass
    coords_json = json.dumps(city_coords)

    html += f"""
<main class="max-w-5xl mx-auto px-4 py-10">
  <nav aria-label="Breadcrumb" class="text-xs text-slate-500 mb-3"><a href="/" class="hover:text-brand-700">Home</a> <span class="mx-1">›</span> <span class="text-slate-700">Crime near me</span></nav>

  <section class="text-center mb-8">
    <h1 class="text-4xl md:text-5xl font-bold text-slate-900 mb-3">Crime near me</h1>
    <p class="text-lg text-slate-600 max-w-2xl mx-auto">Find your city's crime map and predicted risk overlay. We'll offer to detect your location — or you can pick a city below.</p>
  </section>

  <section id="geoBox" class="bg-white border border-slate-200 rounded-lg p-6 mb-8 text-center">
    <button id="locateBtn" type="button" class="inline-flex items-center gap-2 bg-brand-700 text-white px-6 py-3 rounded-lg font-bold text-base hover:bg-brand-800 transition">📍 Use my location</button>
    <p id="geoStatus" class="text-sm text-slate-500 mt-3">We'll ask your browser for permission. Location is used once, in your browser, and never stored.</p>
  </section>

  <section class="mb-10">
    <h2 class="text-2xl font-bold text-slate-900 mb-4">Or pick a city</h2>
    <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">{picker}</div>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-6 text-slate-700 leading-relaxed">
    <h2 class="text-xl font-bold text-slate-900 mb-2">Why {SITE_NAME} for "crime near me"?</h2>
    <p class="mb-2">Every city we cover has a fully-crawlable map page with the last ~45 days of reported incidents, filtering, an incident table, and a predicted-risk overlay from our machine learning model. There's no login. No app. No paywall.</p>
    <p class="text-sm text-slate-500 mb-0">For real-time notifications when new crime is reported near a specific address, use <a class="text-brand-700 hover:underline" href="https://spotcrime.com" target="_blank" rel="noopener">SpotCrime</a>'s free daily email alerts — they cover thousands more US cities than we do.</p>
  </section>
</main>

<script>
(function() {{
  const CITIES = {coords_json};
  const locate = document.getElementById('locateBtn');
  const status = document.getElementById('geoStatus');
  if (!('geolocation' in navigator)) {{ locate.disabled = true; status.textContent = 'Your browser does not support geolocation. Pick a city below.'; return; }}
  function nearest(lat, lng) {{
    const R = 6371; let best = null; let bestKm = Infinity;
    for (const c of CITIES) {{
      const dLat = (c.lat - lat) * Math.PI / 180;
      const dLng = (c.lng - lng) * Math.PI / 180;
      const a = Math.sin(dLat/2)**2 + Math.cos(lat*Math.PI/180) * Math.cos(c.lat*Math.PI/180) * Math.sin(dLng/2)**2;
      const km = 2 * R * Math.asin(Math.sqrt(a));
      if (km < bestKm) {{ bestKm = km; best = c; }}
    }}
    return {{ city: best, km: bestKm }};
  }}
  locate.addEventListener('click', () => {{
    status.textContent = 'Looking up your nearest city…';
    navigator.geolocation.getCurrentPosition((pos) => {{
      const {{ latitude, longitude }} = pos.coords;
      const {{ city, km }} = nearest(latitude, longitude);
      if (!city) {{ status.textContent = 'No cities available. Pick one below.'; return; }}
      if (km > 300) {{
        status.innerHTML = `Nearest city we cover is <strong>${{city.name}}, ${{city.state}}</strong> (about ${{Math.round(km)}} km away). We may not cover your area yet — <a class="text-brand-700 underline" href="https://spotcrime.com" target="_blank" rel="noopener">SpotCrime</a> covers thousands more US cities.`;
        return;
      }}
      status.innerHTML = `Redirecting to <strong>${{city.name}}, ${{city.state}}</strong> (${{Math.round(km)}} km away)…`;
      setTimeout(() => {{ window.location.href = '/' + city.slug; }}, 700);
    }}, (err) => {{ status.textContent = 'Location permission denied or unavailable. Pick a city below.'; }},
    {{ enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }});
  }});
}})();
</script>
"""
    html += alerts_cta("your city", "https://spotcrime.com")
    html += footer(summary[0]["generated_at"] if summary else "", n)
    return html


# ─── Neighborhood pages ────────────────────────────────────────────────
def neighborhood_page(city: dict, summary: list[dict], hood_name: str,
                     hood_incidents: list[dict], all_hoods: dict) -> str:
    slug = city["slug"]
    hslug = hood_slug(hood_name)
    city_name = city["city"]
    state = city["state_abbrev"]
    name_state = _city_with_state(city_name, state)
    hood_count = len(hood_incidents)

    hood_cats: dict[str, int] = {}
    for inc in hood_incidents:
        cat = inc.get("category") or "Unclassified"
        hood_cats[cat] = hood_cats.get(cat, 0) + 1
    hood_cats = dict(sorted(hood_cats.items(), key=lambda kv: -kv[1]))
    top_cat = next(iter(hood_cats), "") if hood_cats else ""
    top_cat_n = hood_cats.get(top_cat, 0) if top_cat else 0

    counts = sorted(g["count"] for g in all_hoods.values())
    median = counts[len(counts) // 2] if counts else 0
    lower = sum(1 for c in counts if c < hood_count)
    pct = int(100 * lower / max(1, len(counts)))

    # Ordinal suffix for percentile
    if 10 <= pct % 100 <= 20:
        pct_str = f"{pct}th"
    else:
        pct_str = f"{pct}{ {1:'st', 2:'nd', 3:'rd'}.get(pct % 10, 'th') }"

    if hood_count > median * 1.5:
        comparison = f"higher-incident than most {city_name} neighborhoods (about the {pct_str} percentile in this window)"
    elif hood_count < median * 0.5 and hood_count > 0:
        comparison = f"lower-incident than most {city_name} neighborhoods (about the {pct_str} percentile in this window)"
    else:
        comparison = f"near the median for {city_name} neighborhoods"

    top3_str = ", ".join(f"{v} {k.lower()}" for k, v in list(hood_cats.items())[:3])

    title = f"{hood_name} crime map ({city_name}, {state}) — {hood_count} recent incidents | {SITE_NAME}"
    description = (
        f"Crime map and incident data for {hood_name} in {city_name}, {state}. "
        f"{hood_count} reported incidents in the last {city['window_days']} days"
        + (f": {top3_str}. " if top3_str else ". ")
        + f"See predicted risk, incident table, and how {hood_name} compares to other {city_name} neighborhoods."
    )
    keywords = ", ".join([f"{hood_name} crime", f"{hood_name} {city_name}", f"{hood_name} crime map", f"crime near me {hood_name}", f"{hood_name} safety", f"{city_name} neighborhood crime"])

    json_ld = [
        _org_ld(),
        _breadcrumb_ld([("Home", f"{BASE_URL}/"), (f"{city_name}, {state}", f"{BASE_URL}/{slug}"), (hood_name, f"{BASE_URL}/{slug}/{hslug}")]),
        {"@context": "https://schema.org", "@type": "Place", "name": f"{hood_name}, {city_name}, {state}",
         "containedInPlace": {"@type": "City", "name": f"{city_name}, {state}", "url": f"{BASE_URL}/{slug}"}},
    ]

    others = sorted([(n, g) for n, g in all_hoods.items() if n != hood_name],
                    key=lambda x: -x[1]["count"])[:8]
    other_links = "".join(
        f"<a href='/{slug}/{g['slug']}' class='inline-block bg-slate-100 hover:bg-brand-50 hover:text-brand-800 text-slate-700 rounded px-3 py-1 text-sm mr-2 mb-2'>{n} <span class='text-xs text-slate-500'>({g['count']})</span></a>"
        for n, g in others
    )

    hood_legend = legend(hood_cats)
    preview_rows = _incident_preview(hood_incidents, limit=10)

    html = head(title, description, f"{BASE_URL}/{slug}/{hslug}", keywords=keywords, og_type="article", json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(slug, summary)

    hood_data_json = json.dumps({"incidents": hood_incidents, "center": city["map_center"], "zoom": max(13, city["map_zoom"] + 1)})
    cat_color_js = json.dumps(CATEGORY_COLORS)

    top_cat_prose = f"<p class='mb-2'>The most common category in {hood_name} right now is <strong>{top_cat}</strong> ({top_cat_n} incidents).</p>" if top_cat else ""

    html += f"""
<main class="max-w-7xl mx-auto px-4 py-8">
  <nav aria-label="Breadcrumb" class="text-xs text-slate-500 mb-3">
    <a href="/" class="hover:text-brand-700">Home</a> <span class="mx-1">›</span>
    <a href="/{slug}" class="hover:text-brand-700">{name_state}</a> <span class="mx-1">›</span>
    <span class="text-slate-700">{hood_name}</span>
  </nav>

  <section class="mb-6">
    <h1 class="text-3xl md:text-4xl font-bold tracking-tight mb-1">{hood_name} crime map</h1>
    <p class="text-slate-600">{hood_count:,} reported incidents in {hood_name}, {city_name} · last {city['window_days']} days</p>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-3 mb-4">
    <div id="map" style="height: 480px;" class="rounded" aria-label="Interactive crime map of {hood_name}, {city_name}"></div>
    <div class="mt-3">{hood_legend}</div>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-5 mb-8 text-slate-700 text-sm leading-relaxed">
    <h2 class="text-lg font-bold text-slate-900 mb-2">Crime in {hood_name} — the last {city['window_days']} days</h2>
    <p class="mb-2"><strong>{hood_name}</strong> is a neighborhood of {city_name}, {state}. Over the last {city['window_days']} days, {hood_count:,} reported incidents landed in the neighborhood — which is <strong>{comparison}</strong>.</p>
    {top_cat_prose}
    <p class="text-xs text-slate-500">Data source: <a href="{city['data_source_url']}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">{city['data_source']}</a>. For real-time alerts near a specific address in {hood_name}, sign up for free daily email alerts on <a href="{city['spotcrime_alerts_url']}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">SpotCrime</a>.</p>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-4 mb-8">
    <h2 class="text-lg font-bold mb-3">Recent incidents in {hood_name}</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-slate-100 text-slate-700"><tr><th class="px-3 py-2 text-left">Date</th><th class="px-3 py-2 text-left">Category</th><th class="px-3 py-2 text-left">Offense</th><th class="px-3 py-2 text-left">Address</th></tr></thead>
        <tbody id="incidentTable">
{preview_rows}
        </tbody>
      </table>
    </div>
  </section>

  <section class="mb-8">
    <h2 class="text-lg font-bold text-slate-900 mb-3">Other {city_name} neighborhoods</h2>
    <div>{other_links}</div>
    <p class="mt-3"><a href="/{slug}" class="text-brand-700 font-semibold hover:underline">See all of {city_name} →</a></p>
  </section>
</main>
"""
    html += alerts_cta(city_name, city["spotcrime_alerts_url"])
    html += footer(city["generated_at"], len(summary))

    html += f"""
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(function() {{
  const CAT_COLORS = {cat_color_js};
  const DATA = {hood_data_json};
  const incidents = DATA.incidents;
  const map = L.map('map').setView(DATA.center, DATA.zoom);
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }}).addTo(map);
  const layer = L.layerGroup();
  const bounds = [];
  for (const inc of incidents) {{
    const color = CAT_COLORS[inc.category || 'Unclassified'] || '#64748b';
    const m = L.circleMarker([inc.lat, inc.lng], {{ radius: 5, fillColor: color, color: color, weight: 1, opacity: 0.9, fillOpacity: 0.65 }});
    m.bindPopup(`<div class="text-sm"><div class="font-bold">${{inc.category || 'Unclassified'}}</div><div>${{inc.description || ''}}</div><div class="text-slate-600">${{inc.address || ''}}</div><div class="text-slate-500 text-xs">${{inc.datetime ? new Date(inc.datetime).toLocaleString() : ''}}</div></div>`);
    layer.addLayer(m);
    bounds.push([inc.lat, inc.lng]);
  }}
  layer.addTo(map);
  if (bounds.length > 1) {{ try {{ map.fitBounds(bounds, {{ padding: [20, 20], maxZoom: 16 }}); }} catch (e) {{}} }}
  const tbody = document.getElementById('incidentTable');
  tbody.innerHTML = incidents.slice(0, 100).map(i => {{
    const color = CAT_COLORS[i.category || 'Unclassified'] || '#64748b';
    const dt = i.datetime ? new Date(i.datetime) : null;
    const dtStr = dt && !isNaN(dt) ? dt.toLocaleString([], {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }}) : '—';
    return `<tr class="border-b border-slate-100"><td class="px-3 py-2 text-slate-700 whitespace-nowrap">${{dtStr}}</td><td class="px-3 py-2"><span class="inline-flex items-center gap-1"><span class="legend-dot" style="background:${{color}}"></span>${{i.category || 'Unclassified'}}</span></td><td class="px-3 py-2 text-slate-700">${{i.description || ''}}</td><td class="px-3 py-2 text-slate-700">${{i.address || ''}}</td></tr>`;
  }}).join('');
}})();
</script>
"""
    return html


# ─── Category pages ─────────────────────────────────────────────────────
def category_page(city: dict, summary: list[dict], category: str, incidents_for_cat: list[dict]) -> str:
    slug = city["slug"]
    cat_slug = category.lower()
    city_name = city["city"]
    state = city["state_abbrev"]
    name_state = _city_with_state(city_name, state)
    n = len(incidents_for_cat)

    title = f"{category} in {city_name}, {state} — {n:,} recent incidents | {SITE_NAME}"
    description = (
        f"Interactive map of {n:,} reported {category.lower()} incidents in {city_name}, "
        f"{state} from the last {city['window_days']} days. Data from {city['data_source']}."
    )
    keywords = ", ".join([f"{category} in {city_name}", f"{city_name} {category.lower()}", f"{category.lower()} near me {city_name}", f"{category.lower()} map {city_name}", f"{city_name} crime rate"])
    json_ld = [
        _org_ld(),
        _breadcrumb_ld([("Home", f"{BASE_URL}/"), (f"{city_name}, {state}", f"{BASE_URL}/{slug}"), (category, f"{BASE_URL}/{slug}/{cat_slug}")]),
    ]
    all_cats = list(city["category_counts"].keys())
    sibling_cats = "".join(
        f"<a href='/{slug}/{c.lower()}' class='inline-block bg-slate-100 hover:bg-brand-50 hover:text-brand-800 text-slate-700 rounded px-3 py-1 text-sm mr-2 mb-2'>{c} <span class='text-xs text-slate-500'>({city['category_counts'][c]})</span></a>"
        for c in all_cats if c != category
    )
    cat_color_js = json.dumps(CATEGORY_COLORS)
    map_center_js = json.dumps(city["map_center"])
    map_zoom_js = city["map_zoom"]
    incidents_json = json.dumps(incidents_for_cat[:1000])
    preview_rows = _incident_preview(incidents_for_cat, limit=10)

    html = head(title, description, f"{BASE_URL}/{slug}/{cat_slug}", keywords=keywords, og_type="article", json_ld=json_ld)
    html += '<body class="bg-slate-50 text-slate-900">'
    html += nav(slug, summary)
    html += f"""
<main class="max-w-7xl mx-auto px-4 py-8">
  <nav aria-label="Breadcrumb" class="text-xs text-slate-500 mb-3">
    <a href="/" class="hover:text-brand-700">Home</a> <span class="mx-1">›</span>
    <a href="/{slug}" class="hover:text-brand-700">{name_state}</a> <span class="mx-1">›</span>
    <span class="text-slate-700">{category}</span>
  </nav>
  <section class="mb-6">
    <h1 class="text-3xl md:text-4xl font-bold tracking-tight mb-1">{category} in {name_state}</h1>
    <p class="text-slate-600">{n:,} recent {category.lower()} incidents · last {city['window_days']} days</p>
  </section>
  <section class="bg-white border border-slate-200 rounded-lg p-3 mb-4">
    <div id="map" style="height: 520px;" class="rounded" aria-label="Map of {category} incidents in {name_state}"></div>
  </section>
  <section class="bg-white border border-slate-200 rounded-lg p-5 mb-8 text-slate-700 text-sm leading-relaxed">
    <h2 class="text-lg font-bold text-slate-900 mb-2">About {category.lower()} in {city_name}</h2>
    <p class="mb-2">This page shows only <strong>{category.lower()} incidents</strong> in {name_state} from the last {city['window_days']} days — {n:,} reports in total, filtered from the full {city_name} dataset.</p>
    <p class="mb-2">For all crime categories in {city_name} on one map, <a href="/{slug}" class="text-brand-700 hover:underline font-semibold">see the full {city_name} crime map</a>.</p>
  </section>
  <section class="bg-white border border-slate-200 rounded-lg p-4 mb-8">
    <h2 class="text-lg font-bold mb-3">Recent {category.lower()} incidents</h2>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead class="bg-slate-100 text-slate-700"><tr><th class="px-3 py-2 text-left">Date</th><th class="px-3 py-2 text-left">Offense</th><th class="px-3 py-2 text-left">Address</th></tr></thead>
        <tbody id="incidentTable">
{preview_rows}
        </tbody>
      </table>
    </div>
  </section>
  <section class="mb-8">
    <h2 class="text-lg font-bold text-slate-900 mb-3">Other categories in {city_name}</h2>
    <div>{sibling_cats}</div>
  </section>
</main>
"""
    html += alerts_cta(city_name, city["spotcrime_alerts_url"])
    html += footer(city["generated_at"], len(summary))
    html += f"""
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(function() {{
  const CAT_COLORS = {cat_color_js};
  const incidents = {incidents_json};
  const map = L.map('map').setView({map_center_js}, {map_zoom_js});
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' }}).addTo(map);
  const color = CAT_COLORS['{category}'] || '#64748b';
  const bounds = [];
  for (const inc of incidents) {{
    const m = L.circleMarker([inc.lat, inc.lng], {{ radius: 4, fillColor: color, color: color, weight: 1, opacity: 0.9, fillOpacity: 0.6 }});
    m.bindPopup(`<div class="text-sm"><div class="font-bold">{category}</div><div>${{inc.description || ''}}</div><div class="text-slate-600">${{inc.address || ''}}</div><div class="text-slate-500 text-xs">${{inc.datetime ? new Date(inc.datetime).toLocaleString() : ''}}</div></div>`);
    m.addTo(map);
    bounds.push([inc.lat, inc.lng]);
  }}
  if (bounds.length > 1) {{ try {{ map.fitBounds(bounds, {{ padding: [20, 20], maxZoom: 15 }}); }} catch (e) {{}} }}
  const tbody = document.getElementById('incidentTable');
  tbody.innerHTML = incidents.slice(0, 100).map(i => {{
    const dt = i.datetime ? new Date(i.datetime) : null;
    const dtStr = dt && !isNaN(dt) ? dt.toLocaleString([], {{ month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }}) : '—';
    return `<tr class="border-b border-slate-100"><td class="px-3 py-2 text-slate-700 whitespace-nowrap">${{dtStr}}</td><td class="px-3 py-2 text-slate-700">${{i.description || ''}}</td><td class="px-3 py-2 text-slate-700">${{i.address || ''}}</td></tr>`;
  }}).join('');
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
    entries.append(_entry(f"{BASE_URL}/predictions", "0.9", "weekly"))
    entries.append(_entry(f"{BASE_URL}/near-me", "0.9", "weekly"))
    entries.append(_entry(f"{BASE_URL}/methodology", "0.7", "monthly"))
    entries.append(_entry(f"{BASE_URL}/about", "0.6", "monthly"))
    entries.append(_entry(f"{BASE_URL}/faq", "0.6", "monthly"))
    for c in summary:
        slug = c["slug"]
        entries.append(_entry(f"{BASE_URL}/{slug}", "0.8", "daily"))
        # Neighborhood + category pages per city
        src = DATA_DIR / f"{slug}.json"
        if src.exists():
            try:
                full = json.loads(src.read_text())
                incidents = full.get("incidents", [])
                # Categories
                cats_in_data: dict[str, int] = {}
                for inc in incidents:
                    cat = inc.get("category") or "Unclassified"
                    cats_in_data[cat] = cats_in_data.get(cat, 0) + 1
                for cat, cnt in cats_in_data.items():
                    if cnt >= 3 and cat != "Unclassified":
                        entries.append(_entry(f"{BASE_URL}/{slug}/{cat.lower()}", "0.6", "daily"))
                # Neighborhoods
                if city_supports_hoods(slug):
                    groups = group_incidents_by_hood(slug, incidents)
                    for hood_name, g in groups.items():
                        if g["count"] >= 3:
                            entries.append(_entry(f"{BASE_URL}/{slug}/{g['slug']}", "0.6", "daily"))
            except Exception:
                pass
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

    # Index / About / FAQ / Predictions / Methodology / Near-me
    (OUT_DIR / "index.html").write_text(index_page(summary))
    print("[gen] wrote index.html")
    (OUT_DIR / "about.html").write_text(about_page(summary))
    print("[gen] wrote about.html")
    (OUT_DIR / "faq.html").write_text(faq_page(summary))
    print("[gen] wrote faq.html")
    (OUT_DIR / "predictions.html").write_text(predictions_page(summary))
    print("[gen] wrote predictions.html")
    (OUT_DIR / "methodology.html").write_text(methodology_page(summary))
    print("[gen] wrote methodology.html")
    (OUT_DIR / "near-me.html").write_text(near_me_page(summary))
    print("[gen] wrote near-me.html")

    # Neighborhood + category pages per city
    n_hood_pages = 0
    n_cat_pages = 0
    for s in summary:
        slug = s["slug"]
        src = DATA_DIR / f"{slug}.json"
        if not src.exists():
            continue
        full = json.loads(src.read_text())
        incidents = full.get("incidents", [])

        # Neighborhood pages
        if city_supports_hoods(slug):
            groups = group_incidents_by_hood(slug, incidents)
            city_dir = OUT_DIR / slug
            if groups:
                city_dir.mkdir(exist_ok=True)
                for hood_name, g in groups.items():
                    if g["count"] < 3:
                        continue  # skip ultra-thin pages; keep the noise floor honest
                    page = neighborhood_page(full, summary, hood_name, g["incidents"], groups)
                    (city_dir / f"{g['slug']}.html").write_text(page)
                    n_hood_pages += 1

        # Category pages (skip categories with < 3 incidents in the window)
        cats_in_data: dict[str, list[dict]] = {}
        for inc in incidents:
            c = inc.get("category") or "Unclassified"
            cats_in_data.setdefault(c, []).append(inc)
        city_dir = OUT_DIR / slug
        for cat, cat_incs in cats_in_data.items():
            if len(cat_incs) < 3:
                continue
            if cat == "Unclassified":
                continue  # not a useful landing target
            city_dir.mkdir(exist_ok=True)
            page = category_page(full, summary, cat, cat_incs)
            (city_dir / f"{cat.lower()}.html").write_text(page)
            n_cat_pages += 1
    print(f"[gen] wrote {n_hood_pages} neighborhood pages, {n_cat_pages} category pages")

    # SEO artefacts
    (OUT_DIR / "robots.txt").write_text(robots_txt())
    print("[gen] wrote robots.txt")
    (OUT_DIR / "sitemap.xml").write_text(sitemap_xml(summary))
    print("[gen] wrote sitemap.xml")
    (OUT_DIR / "favicon.svg").write_text(favicon_svg())
    print("[gen] wrote favicon.svg")

    # IndexNow verification file (Bing / Yandex / Seznam / Naver)
    (OUT_DIR / f"{INDEXNOW_KEY}.txt").write_text(INDEXNOW_KEY + "\n")
    print(f"[gen] wrote {INDEXNOW_KEY}.txt (IndexNow key)")

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
