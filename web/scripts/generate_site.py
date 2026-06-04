#!/usr/bin/env python3
"""Generate the static site (index + per-city pages) from data/*.json.

Output: citymaps/pages/index.html and citymaps/pages/<slug>.html plus a
copy of /data/<slug>.json into citymaps/pages/data/.

After running, citymaps/pages/ is the static-deployable site root.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "pages"
OUT_DATA_DIR = OUT_DIR / "data"

# Canonical domain for SEO (og:url, <link rel="canonical">).
# Override via env: BASE_URL=https://citymaps.vercel.app python generate_site.py
import os
BASE_URL = os.environ.get("BASE_URL", "https://citycrimemap.us").rstrip("/")

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


def head(title: str, description: str, canonical: str) -> str:
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>{title}</title>
  <meta name=\"description\" content=\"{description}\">
  <link rel=\"canonical\" href=\"{canonical}\">
  <meta property=\"og:title\" content=\"{title}\">
  <meta property=\"og:description\" content=\"{description}\">
  <meta property=\"og:type\" content=\"website\">
  <meta property=\"og:url\" content=\"{canonical}\">
  <link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\" integrity=\"sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=\" crossorigin=\"\">
  <script src=\"https://cdn.tailwindcss.com\"></script>
  <script>
    tailwind.config = {{ theme: {{ extend: {{ colors: {{
      brand: {{ 50:'#fef2f2', 100:'#fee2e2', 500:'#ef4444', 600:'#dc2626', 700:'#b91c1c', 800:'#991b1b' }}
    }} }} }} }};
  </script>
  <style>
    .leaflet-container {{ background:#1f2937; }}
    .legend-dot {{ width: 0.75rem; height: 0.75rem; border-radius: 9999px; display:inline-block; margin-right:0.4rem; vertical-align:middle; }}
  </style>
</head>
"""


def nav(active_slug: str | None, summary: list[dict]) -> str:
    items = ['<a href="./index.html" class="hover:text-brand-100 ' + ("font-bold text-white" if active_slug is None else "text-brand-100/80") + '">All cities</a>']
    for c in summary:
        cls = "font-bold text-white" if c["slug"] == active_slug else "text-brand-100/80 hover:text-brand-100"
        items.append(f'<a href="./{c["slug"]}.html" class="{cls}">{c["name"]}</a>')
    return f"""
<header class="bg-brand-700 text-white">
  <div class="max-w-7xl mx-auto px-4 py-4 flex flex-wrap items-center justify-between gap-4">
    <a href="./index.html" class="text-xl font-bold tracking-tight">🚨 CityCrimeMaps</a>
    <nav class="flex flex-wrap gap-x-5 gap-y-1 text-sm">
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
      SpotCrime sends you a daily email with crimes reported near any address you choose.
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


def footer(generated_at: str) -> str:
    return f"""
<footer class="bg-slate-900 text-slate-300 mt-12">
  <div class="max-w-7xl mx-auto px-4 py-8 grid md:grid-cols-3 gap-6 text-sm">
    <div>
      <p class="font-bold text-white mb-2">CityCrimeMaps</p>
      <p>Free public-data crime maps for five US cities, refreshed from city open-data portals via <a href="https://github.com/Steal-This-Code/tidycops" class="text-brand-500 hover:text-brand-100" target="_blank" rel="noopener">tidycop</a>.</p>
    </div>
    <div>
      <p class="font-bold text-white mb-2">Want alerts for another city?</p>
      <p><a href="https://spotcrime.com" target="_blank" rel="noopener" class="text-brand-500 hover:text-brand-100">SpotCrime covers thousands of cities →</a></p>
    </div>
    <div>
      <p class="font-bold text-white mb-2">Data freshness</p>
      <p>Last generated: <span class="font-mono">{generated_at}</span></p>
      <p class="text-slate-400 text-xs mt-2">Crime data comes from city open-data portals and may lag the real world by days to weeks. For real-time alerts, sign up at <a href="https://spotcrime.com" target="_blank" rel="noopener" class="text-brand-500">SpotCrime</a>.</p>
    </div>
  </div>
</footer>
</body></html>
"""


def index_page(summary: list[dict]) -> str:
    cards = []
    for c in summary:
        cats = c["category_counts"]
        top_cats = ", ".join(f"{k} ({v})" for k, v in list(cats.items())[:4])
        cards.append(f"""
        <a href="./{c['slug']}.html" class="block bg-white border border-slate-200 rounded-lg shadow-sm hover:shadow-md transition p-5">
          <div class="flex items-start justify-between mb-3">
            <h3 class="text-xl font-bold text-slate-900">{c['name']}, {c['state_abbrev']}</h3>
            <span class="text-xs font-mono text-slate-500">{c['row_count']:,} incidents</span>
          </div>
          <p class="text-sm text-slate-600 mb-3">Last {c['window_days']} days</p>
          <p class="text-xs text-slate-500"><span class="font-semibold">Top categories:</span> {top_cats}</p>
          <p class="text-brand-600 text-sm font-semibold mt-3">View map and table →</p>
        </a>""")
    n = len(summary)
    city_list_short = ", ".join(c["name"] for c in summary[:6])
    if n > 6:
        city_list_short += f", and {n - 6} more"
    html = head(
        f"City Crime Maps | Interactive maps for {n} US cities",
        f"Interactive crime maps and incident tables for {n} US cities ({city_list_short}). Free crime alerts powered by SpotCrime.",
        f"{BASE_URL}/",
    )
    html += "<body class=\"bg-slate-50 text-slate-900\">"
    html += nav(None, summary)
    html += f"""
<main class="max-w-7xl mx-auto px-4 py-10">
  <section class="text-center mb-10">
    <h1 class="text-4xl md:text-5xl font-bold tracking-tight mb-3">Crime maps for {n} US cities</h1>
    <p class="text-slate-600 max-w-2xl mx-auto text-lg">Interactive maps and incident tables from open city data. Updated regularly. Want crime alerts for your neighborhood? <a href="https://spotcrime.com" target="_blank" rel="noopener" class="text-brand-700 font-semibold hover:underline">Sign up free at SpotCrime</a>.</p>
  </section>
  <section class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
"""
    html += "\n".join(cards)
    html += """
  </section>
</main>
"""
    html += alerts_cta("your city", "https://spotcrime.com")
    html += footer(summary[0]["generated_at"] if summary else "")
    return html


def legend(cats: dict[str, int]) -> str:
    items = []
    for cat, count in cats.items():
        color = CATEGORY_COLORS.get(cat, "#64748b")
        items.append(
            f'<span class="inline-flex items-center text-xs mr-3 mb-1"><span class="legend-dot" style="background:{color}"></span><span class="text-slate-700">{cat}</span><span class="text-slate-400 ml-1">({count})</span></span>'
        )
    return "<div class=\"flex flex-wrap\">" + "".join(items) + "</div>"


def _city_with_state(name: str, state: str) -> str:
    """Avoid duplicating state when name already includes it (e.g. "Washington, DC")."""
    if name.endswith(f", {state}"):
        return name
    return f"{name}, {state}"


def city_page(city: dict, summary: list[dict]) -> str:
    name = city["city"]
    slug = city["slug"]
    state = city["state_abbrev"]
    cats = city["category_counts"]
    name_state = _city_with_state(name, state)
    html = head(
        f"{name_state} Crime Map | Recent Incidents & Free Alerts",
        f"{name} crime map and incident table — last {city['window_days']} days of reported crime in {name_state}. Sign up for free crime alerts.",
        f"{BASE_URL}/{slug}",
    )
    html += "<body class=\"bg-slate-50 text-slate-900\">"
    html += nav(slug, summary)
    html += f"""
<main class="max-w-7xl mx-auto px-4 py-8">
  <section class="mb-6">
    <h1 class="text-3xl md:text-4xl font-bold tracking-tight mb-1">{name_state} crime map</h1>
    <p class="text-slate-600">{city['row_count']:,} incidents · last {city['window_days']} days · source: <a href="{city['data_source_url']}" target="_blank" rel="noopener" class="text-brand-700 hover:underline">{city['data_source']}</a></p>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-3 mb-4">
    <div id="map" style="height: 520px;" class="rounded"></div>
    <div class="mt-3">{legend(cats)}</div>
  </section>

  <section class="bg-white border border-slate-200 rounded-lg p-4 mb-8">
    <div class="flex flex-wrap items-center justify-between gap-3 mb-3">
      <h2 class="text-lg font-bold">Recent incidents</h2>
      <div class="flex flex-wrap gap-2 items-center">
        <label class="text-sm text-slate-600">Filter:</label>
        <select id="catFilter" class="border border-slate-300 rounded px-2 py-1 text-sm">
          <option value="">All categories</option>
        </select>
        <input id="searchFilter" type="search" placeholder="Search address or offense…" class="border border-slate-300 rounded px-2 py-1 text-sm w-56">
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
        <tbody id="incidentTable"></tbody>
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
    html += footer(city["generated_at"])

    # Page-specific JS
    cat_color_js = json.dumps(CATEGORY_COLORS)
    map_center_js = json.dumps(city["map_center"])
    map_zoom_js = city["map_zoom"]
    html += f"""
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js" integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<script>
(async function() {{
  const CAT_COLORS = {cat_color_js};
  const res = await fetch('./data/{slug}.json');
  const data = await res.json();
  const incidents = data.incidents;

  // ── Map ─────────────────────────────────────────────────────────────────
  const map = L.map('map').setView({map_center_js}, {map_zoom_js});
  L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
    maxZoom: 19,
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
  }}).addTo(map);
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
    m.addTo(map);
  }}

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
        full = json.loads(src.read_text())
        page_html = city_page(full, summary)
        (OUT_DIR / f"{slug}.html").write_text(page_html)
        print(f"[gen] wrote {slug}.html ({len(page_html):,} bytes)")

    # Index page
    (OUT_DIR / "index.html").write_text(index_page(summary))
    print(f"[gen] wrote index.html")

    # vercel.json hint (static site)
    (OUT_DIR / "vercel.json").write_text(json.dumps({"cleanUrls": True, "trailingSlash": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
