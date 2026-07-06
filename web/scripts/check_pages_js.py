#!/usr/bin/env python3
"""Smoke-test each generated page by piping its inline <script> body
through ``node --check``.

Motivation: on 2026-07-06 the hotspot help alert() template landed
raw newlines inside a JS string literal, which is a syntax error. It
went unnoticed because ``curl`` returned HTTP 200 and the referenced
data files also returned 200. The map still didn't render because the
inline IIFE failed to parse. This check catches that class of bug in
one step.

Usage:
    ~/Projects/tidycop/.venv/bin/python web/scripts/check_pages_js.py

Exit codes:
    0 — every page's inline JS parses
    1 — one or more pages have broken JS (details on stderr)
    2 — infrastructure failure (missing pages dir, no node in PATH)
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

PAGES = Path(__file__).parent.parent / "pages"
# Match every inline <script> block. Skip external src="..." (empty
# body) and tiny config blocks that would parse fine anyway.
SCRIPT_RE = re.compile(r"<script(?:\s[^>]*)?>(.*?)</script>", re.DOTALL)


def check_file(path: Path) -> list[str]:
    """Return a list of error strings for `path`; empty means clean."""
    errors: list[str] = []
    html = path.read_text()
    blocks = [b for b in SCRIPT_RE.findall(html) if b.strip()]
    for i, body in enumerate(blocks):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as tf:
            tf.write(body)
            tmp = Path(tf.name)
        try:
            result = subprocess.run(
                ["node", "--check", str(tmp)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0:
                errors.append(
                    f"{path.name} block #{i + 1}: {result.stderr.strip()}"
                )
        except FileNotFoundError:
            print("ERROR: `node` not found in PATH", file=sys.stderr)
            sys.exit(2)
        finally:
            tmp.unlink(missing_ok=True)
    return errors


def main() -> int:
    if not PAGES.exists():
        print(f"ERROR: {PAGES} does not exist", file=sys.stderr)
        return 2
    html_files = sorted(PAGES.glob("*.html"))
    if not html_files:
        print(f"ERROR: no .html files in {PAGES}", file=sys.stderr)
        return 2
    total_errors: list[str] = []
    for f in html_files:
        errs = check_file(f)
        if errs:
            total_errors.extend(errs)
            print(f"[check] {f.name}: FAIL")
        else:
            print(f"[check] {f.name}: ok")
    if total_errors:
        print(
            f"\n[check] {len(total_errors)} JS parse error(s) across "
            f"{len(html_files)} page(s):",
            file=sys.stderr,
        )
        for e in total_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"\n[check] all {len(html_files)} pages parse cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
