#!/usr/bin/env python3
"""Push our sitemap URLs to IndexNow (Bing / Yandex / Seznam / Naver).

IndexNow is a lightweight "here are URLs I updated, please recrawl"
protocol. Bing accepts the whole set at once via POST; the other
participants (Yandex, Seznam, Naver) mirror from Bing, so a single
POST to `api.indexnow.org` (or `www.bing.com/indexnow`) reaches all
of them.

Usage:
    python3 web/scripts/indexnow_ping.py               # ping all URLs in sitemap.xml
    python3 web/scripts/indexnow_ping.py --dry-run     # print what we would send

The key file must be reachable at
    https://citycrimemap.us/<KEY>.txt
containing exactly `<KEY>` (this is done automatically by
`generate_site.py`).
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

REPO_ROOT = Path(__file__).resolve().parents[2]
SITEMAP_PATH = REPO_ROOT / "web" / "pages" / "sitemap.xml"

HOST = "citycrimemap.us"
KEY = "6797d8e9f1ba5116256e715981cb7802"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/IndexNow"

# IndexNow accepts up to 10,000 URLs per request.
BATCH_SIZE = 10_000


def load_sitemap_urls(path: Path) -> list[str]:
    tree = ET.parse(path)
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text.strip() for loc in tree.getroot().findall("sm:url/sm:loc", ns) if loc.text]


def post_batch(urls: list[str], *, dry_run: bool = False) -> None:
    body = {
        "host": HOST,
        "key": KEY,
        "keyLocation": KEY_LOCATION,
        "urlList": urls,
    }
    if dry_run:
        print(f"[indexnow] DRY RUN: would POST {len(urls)} urls to {ENDPOINT}")
        print(f"[indexnow]   host={HOST} keyLocation={KEY_LOCATION}")
        print(f"[indexnow]   first 3: {urls[:3]}")
        return
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        status = resp.status
        text = resp.read().decode("utf-8", errors="replace")
    print(f"[indexnow] POST {len(urls)} urls → HTTP {status}")
    if text.strip():
        print(f"[indexnow]   body: {text[:400]}")


def main() -> int:
    p = argparse.ArgumentParser(description="Ping IndexNow with our sitemap URLs.")
    p.add_argument("--dry-run", action="store_true", help="Print what we would send; do not POST.")
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap on URL count (useful for smoke tests).",
    )
    args = p.parse_args()

    if not SITEMAP_PATH.exists():
        print(f"[indexnow] ERROR: sitemap not found at {SITEMAP_PATH}", file=sys.stderr)
        return 2
    urls = load_sitemap_urls(SITEMAP_PATH)
    if args.limit:
        urls = urls[: args.limit]
    if not urls:
        print("[indexnow] no URLs in sitemap; nothing to do", file=sys.stderr)
        return 1
    print(f"[indexnow] loaded {len(urls)} urls from {SITEMAP_PATH}")

    # Verify the key file is reachable before we bother the endpoint;
    # IndexNow will 403 the whole batch if the key isn't served.
    try:
        with urllib.request.urlopen(KEY_LOCATION, timeout=10) as resp:
            served = resp.read().decode("utf-8").strip()
        if served != KEY:
            print(
                f"[indexnow] ERROR: key file at {KEY_LOCATION} does not match ({served!r} vs {KEY!r})",
                file=sys.stderr,
            )
            return 3
        print(f"[indexnow] key file OK at {KEY_LOCATION}")
    except Exception as exc:
        print(f"[indexnow] ERROR: could not fetch key file at {KEY_LOCATION}: {exc}", file=sys.stderr)
        return 3

    for start in range(0, len(urls), BATCH_SIZE):
        batch = urls[start : start + BATCH_SIZE]
        post_batch(batch, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
