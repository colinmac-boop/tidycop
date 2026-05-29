"""Command-line interface for tidycop.

Entry point wired via ``[tool.poetry.scripts] tidycop = "tidycop.cli:main"``.

Subcommands:
    fetch    Fetch incidents for one city + date window, write to stdout or file.
    cities   List supported cities (canonical key, providers, source count).

Examples::

    tidycop fetch chicago --start 2026-04-01 --end 2026-04-07 --output csv
    tidycop fetch sf --start 2026-04-01 --end 2026-04-30 --view city_full \\
        --output parquet --out-path /tmp/sf_april.parquet
    tidycop cities
    tidycop cities --provider arcgis

Design notes:
    - argparse only (no click) — keeps deps minimal per project policy.
    - For ``--output parquet`` we let pandas raise its own ImportError if
      pyarrow/fastparquet isn't installed; that's a friendlier error than
      pre-checking + reformatting.
    - stdout path is "-"; default ``--out-path`` is stdout for csv/json,
      and a required positional for parquet (parquet can't really stream).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from tidycop import __version__
from tidycop.core import get_incidents
from tidycop.registry import list_supported_cities, load_registry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str) -> date:
    """argparse type=... helper."""
    try:
        return datetime.fromisoformat(value).date()
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"invalid date {value!r}: {e}") from e


def _serialize_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Render timezone-aware datetimes as ISO-8601 strings for csv/json output.

    Parquet handles tz-aware datetimes natively, so we skip this there.
    """
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[col]):
            out[col] = out[col].apply(lambda v: None if pd.isna(v) else v.isoformat())
    return out


def _write_output(df: pd.DataFrame, fmt: str, out_path: str | None) -> None:
    fmt = fmt.lower()
    if fmt == "csv":
        df_out = _serialize_dates(df)
        if out_path in (None, "-"):
            df_out.to_csv(sys.stdout, index=False)
        else:
            df_out.to_csv(out_path, index=False)
    elif fmt == "json":
        df_out = _serialize_dates(df)
        records = df_out.to_dict(orient="records")
        text = json.dumps(records, indent=2, default=str)
        if out_path in (None, "-"):
            sys.stdout.write(text)
            sys.stdout.write("\n")
        else:
            Path(out_path).write_text(text)
    elif fmt == "parquet":
        if out_path in (None, "-"):
            raise SystemExit(
                "error: --out-path is required for --output parquet (cannot stream parquet to stdout)"
            )
        df.to_parquet(out_path, index=False)
    else:
        raise SystemExit(f"error: unknown --output {fmt!r}; expected csv | json | parquet")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_fetch(args: argparse.Namespace) -> int:
    try:
        df = get_incidents(
            args.city,
            args.start,
            args.end,
            view=args.view,
            limit=args.limit,
            classify_spotcrime=args.classify_spotcrime,
            registry_path=args.registry_path,
        )
    except KeyError as e:
        # unknown city
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except ImportError as e:
        # e.g. --classify-spotcrime without tidycop-spotcrime installed.
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(
        f"tidycop: {args.city} {args.start}..{args.end} → {len(df):,} rows "
        f"(view={args.view}, output={args.output})",
        file=sys.stderr,
    )
    _write_output(df, args.output, args.out_path)
    return 0


def cmd_cities(args: argparse.Namespace) -> int:
    if args.registry_path:
        # Render the overlay registry directly (bypasses the default cache).
        from tidycop.registry import _build_city  # noqa: F401  (already loaded)
        overlay = load_registry(args.registry_path)
        cities = [
            {
                "city": key,
                "display_name": spec.display_name,
                "timezone": spec.timezone,
                "aliases": list(spec.aliases),
                "providers": sorted({s.provider for s in spec.sources}),
                "source_count": len(spec.sources),
            }
            for key, spec in overlay.items()
        ]
    else:
        cities = list_supported_cities()
    if args.provider:
        cities = [c for c in cities if args.provider in c["providers"]]

    if args.json:
        sys.stdout.write(json.dumps(cities, indent=2))
        sys.stdout.write("\n")
        return 0

    # Plain-text table; intentionally simple (no extra deps).
    width_key = max((len(c["city"]) for c in cities), default=4)
    width_disp = max((len(c["display_name"]) for c in cities), default=12)
    sys.stdout.write(
        f"{'city':<{width_key}}  {'display_name':<{width_disp}}  providers  sources  aliases\n"
    )
    for c in cities:
        provs = ",".join(c["providers"])
        aliases = ",".join(c["aliases"]) if c["aliases"] else "-"
        sys.stdout.write(
            f"{c['city']:<{width_key}}  {c['display_name']:<{width_disp}}  "
            f"{provs:<9}  {c['source_count']:<7}  {aliases}\n"
        )
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="tidycop",
        description="City-agnostic interface for public police incident data.",
    )
    p.add_argument("--version", action="version", version=f"tidycop {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------------ fetch
    pf = sub.add_parser("fetch", help="Fetch incidents for a city + date window.")
    pf.add_argument("city", help="City key or alias (e.g. chicago, sf, pgh, nyc).")
    pf.add_argument("--start", required=True, type=_parse_date, help="Start date YYYY-MM-DD.")
    pf.add_argument(
        "--end", required=True, type=_parse_date, help="End date YYYY-MM-DD (inclusive)."
    )
    pf.add_argument(
        "--output",
        choices=("csv", "json", "parquet"),
        default="csv",
        help="Output format (default: csv to stdout).",
    )
    pf.add_argument(
        "--out-path",
        default=None,
        help="Output file path; defaults to stdout for csv/json. Required for parquet.",
    )
    pf.add_argument(
        "--view",
        choices=("comparable", "city_full", "city_raw"),
        default="comparable",
        help="Column shape: comparable (std_* only), city_full (raw+std), city_raw.",
    )
    pf.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Maximum records to return overall (not per-page). Default: 1000.",
    )
    pf.add_argument(
        "--classify-spotcrime",
        action="store_true",
        help="Add std_spotcrime_category column using the source's mapping.",
    )
    pf.add_argument(
        "--registry-path",
        default=None,
        help=(
            "Path to a downstream registry YAML (e.g. SpotCrime data2 "
            "overlay). When set, the city is resolved from that file "
            "instead of the bundled registry/cities.yaml."
        ),
    )
    pf.set_defaults(func=cmd_fetch)

    # ----------------------------------------------------------------- cities
    pc = sub.add_parser("cities", help="List supported cities.")
    pc.add_argument(
        "--provider",
        choices=("socrata", "arcgis", "ckan"),
        default=None,
        help="Filter by platform provider.",
    )
    pc.add_argument("--json", action="store_true", help="Emit JSON instead of a table.")
    pc.add_argument(
        "--registry-path",
        default=None,
        help="List cities defined in a downstream overlay YAML instead of the bundled registry.",
    )
    pc.set_defaults(func=cmd_cities)

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    rv: Any = args.func(args)
    return int(rv) if rv is not None else 0


if __name__ == "__main__":
    raise SystemExit(main())
