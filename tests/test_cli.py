"""Tests for tidycop.cli."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from tidycop import cli
from tidycop.schema import STD_COLUMNS

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _fake_df(n: int = 3) -> pd.DataFrame:
    rec = {col: None for col in STD_COLUMNS}
    rec["std_city"] = "chicago"
    rec["std_city_display"] = "Chicago"
    rec["std_incident_id"] = "abc123"
    rec["std_offense_description"] = "THEFT"
    rec["std_incident_date"] = pd.Timestamp("2026-04-01 12:00", tz="America/Chicago")
    rows = [dict(rec, std_incident_id=f"id-{i}") for i in range(n)]
    df = pd.DataFrame(rows, columns=STD_COLUMNS)
    df["std_incident_date"] = pd.to_datetime(df["std_incident_date"], utc=True).dt.tz_convert(
        "America/Chicago"
    )
    return df


# ---------------------------------------------------------------------------
# fetch command
# ---------------------------------------------------------------------------


def test_fetch_csv_to_stdout(capsys):
    with patch("tidycop.cli.get_incidents", return_value=_fake_df(2)) as m:
        rc = cli.main(["fetch", "chicago", "--start", "2026-04-01", "--end", "2026-04-02"])
    assert rc == 0
    m.assert_called_once()
    args, kwargs = m.call_args
    assert args[0] == "chicago"
    assert args[1] == date(2026, 4, 1)
    assert args[2] == date(2026, 4, 2)
    assert kwargs == {"view": "comparable", "limit": 1000}

    captured = capsys.readouterr()
    # CSV header on stdout
    assert "std_city" in captured.out
    assert "id-0" in captured.out
    assert "id-1" in captured.out
    # ISO-formatted tz-aware date appears
    assert "2026-04-01T12:00:00" in captured.out
    # Progress line on stderr
    assert "2 rows" in captured.err


def test_fetch_json_to_file(tmp_path: Path):
    out = tmp_path / "out.json"
    with patch("tidycop.cli.get_incidents", return_value=_fake_df(1)):
        rc = cli.main(
            [
                "fetch",
                "chicago",
                "--start",
                "2026-04-01",
                "--end",
                "2026-04-02",
                "--output",
                "json",
                "--out-path",
                str(out),
            ]
        )
    assert rc == 0
    payload = json.loads(out.read_text())
    assert isinstance(payload, list)
    assert payload[0]["std_city"] == "chicago"


def test_fetch_parquet_requires_out_path():
    with patch("tidycop.cli.get_incidents", return_value=_fake_df(1)):
        with pytest.raises(SystemExit) as exc:
            cli.main(
                [
                    "fetch",
                    "chicago",
                    "--start",
                    "2026-04-01",
                    "--end",
                    "2026-04-02",
                    "--output",
                    "parquet",
                ]
            )
    assert "out-path" in str(exc.value).lower() or "out_path" in str(exc.value).lower()


def test_fetch_unknown_city(capsys):
    with patch("tidycop.cli.get_incidents", side_effect=KeyError("unsupported city: 'mars'")):
        rc = cli.main(["fetch", "mars", "--start", "2026-04-01", "--end", "2026-04-02"])
    assert rc == 2
    assert "mars" in capsys.readouterr().err


def test_fetch_invalid_date_format():
    with pytest.raises(SystemExit):
        cli.main(["fetch", "chicago", "--start", "not-a-date", "--end", "2026-04-02"])


def test_fetch_passes_view_and_limit():
    with patch("tidycop.cli.get_incidents", return_value=_fake_df(0)) as m:
        rc = cli.main(
            [
                "fetch",
                "sf",
                "--start",
                "2026-04-01",
                "--end",
                "2026-04-02",
                "--view",
                "city_raw",
                "--limit",
                "50",
            ]
        )
    assert rc == 0
    kwargs = m.call_args.kwargs
    assert kwargs["view"] == "city_raw"
    assert kwargs["limit"] == 50


# ---------------------------------------------------------------------------
# cities command
# ---------------------------------------------------------------------------


def test_cities_table(capsys):
    rc = cli.main(["cities"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "chicago" in out
    assert "providers" in out  # header row
    # All 25 cities should be present
    for city in ("chicago", "detroit", "pittsburgh", "new_york", "houston"):
        assert city in out


def test_cities_filter_provider(capsys):
    rc = cli.main(["cities", "--provider", "ckan"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "pittsburgh" in out
    assert "san_antonio" in out
    # Socrata-only city must not appear
    assert "gainesville" not in out


def test_cities_json(capsys):
    rc = cli.main(["cities", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    keys = {c["city"] for c in payload}
    assert {"chicago", "detroit", "pittsburgh", "new_york"}.issubset(keys)


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "tidycop" in out
