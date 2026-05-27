"""Unit tests for SocrataFetcher.

No network calls — all HTTP responses are mocked. A separate live smoke test
lives in test_socrata_live.py (opt-in via TIDYCOP_LIVE_SOCRATA=1).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from tidycop.platform.socrata import (
    PAGE_SIZE,
    SocrataFetcher,
    SocrataHTTPError,
    _build_where,
)
from tidycop.registry import SourceSpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def chicago_source() -> SourceSpec:
    return SourceSpec(
        source_id="chicago_crimes",
        display_name="Crimes - 2001 to Present",
        provider="socrata",
        dataset_id="ijzp-q8t2",
        base_url="https://data.cityofchicago.org/resource/ijzp-q8t2.json",
        date_field="date",
        field_map={"std_incident_id": "id"},
    )


def _mock_response(
    *, status: int = 200, json_payload: Any = None, content_type: str = "application/json",
    reason: str = "OK", text: str = "", headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.reason = reason
    resp.headers = {"Content-Type": content_type, **(headers or {})}
    resp.text = text or (str(json_payload) if json_payload is not None else "")
    resp.url = "https://example/mock"
    resp.json.return_value = json_payload
    return resp


def _make_fetcher(session: MagicMock, sleeps: list[float] | None = None) -> SocrataFetcher:
    sleeps = sleeps if sleeps is not None else []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    return SocrataFetcher(session=session, sleep=fake_sleep, max_retries=3, initial_backoff=0.01)


# ---------------------------------------------------------------------------
# _build_where
# ---------------------------------------------------------------------------


def test_build_where_inclusive_day_range():
    where = _build_where("date", date(2026, 4, 1), date(2026, 4, 30))
    assert where == "date >= '2026-04-01T00:00:00' AND date < '2026-05-01T00:00:00'"


def test_build_where_single_day_is_one_full_day():
    where = _build_where("date", date(2026, 4, 15), date(2026, 4, 15))
    assert where == "date >= '2026-04-15T00:00:00' AND date < '2026-04-16T00:00:00'"


def test_build_where_rejects_inverted_range():
    with pytest.raises(ValueError):
        _build_where("date", date(2026, 4, 30), date(2026, 4, 1))


# ---------------------------------------------------------------------------
# Single-page fetch
# ---------------------------------------------------------------------------


def test_fetch_happy_path_single_page(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    rows = [{"id": "1"}, {"id": "2"}]
    session.get.return_value = _mock_response(json_payload=rows)

    fetcher = _make_fetcher(session)
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=100)

    assert out == rows
    session.get.assert_called_once()
    _, kwargs = session.get.call_args
    params = kwargs["params"]
    assert params["$where"] == "date >= '2026-04-01T00:00:00' AND date < '2026-05-01T00:00:00'"
    assert params["$order"] == "date ASC"
    assert params["$limit"] == 100  # capped at requested limit, not PAGE_SIZE
    assert params["$offset"] == 0


def test_fetch_sets_user_agent_and_accepts_json(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=[])
    _make_fetcher(session)
    assert session.headers["User-Agent"].startswith("tidycop/")
    assert session.headers["Accept"] == "application/json"


def test_fetch_attaches_app_token_from_env(chicago_source, monkeypatch):
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "tok-abc")
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=[])
    SocrataFetcher(session=session, sleep=lambda s: None)
    assert session.headers["X-App-Token"] == "tok-abc"


def test_fetch_explicit_app_token_overrides_env(chicago_source, monkeypatch):
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "env-token")
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    SocrataFetcher(session=session, app_token="explicit", sleep=lambda s: None)
    assert session.headers["X-App-Token"] == "explicit"


def test_fetch_no_app_token_when_unset(chicago_source, monkeypatch):
    monkeypatch.delenv("SOCRATA_APP_TOKEN", raising=False)
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    SocrataFetcher(session=session, sleep=lambda s: None)
    assert "X-App-Token" not in session.headers


# ---------------------------------------------------------------------------
# Paging
# ---------------------------------------------------------------------------


def test_fetch_pages_until_short_page(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    page1 = [{"id": str(i)} for i in range(PAGE_SIZE)]
    page2 = [{"id": str(i)} for i in range(PAGE_SIZE, PAGE_SIZE + 7)]
    session.get.side_effect = [
        _mock_response(json_payload=page1),
        _mock_response(json_payload=page2),
    ]

    fetcher = _make_fetcher(session)
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10_000)

    assert len(out) == PAGE_SIZE + 7
    assert out[0]["id"] == "0"
    assert out[-1]["id"] == str(PAGE_SIZE + 6)

    # Verify offsets advanced correctly.
    call_offsets = [c.kwargs["params"]["$offset"] for c in session.get.call_args_list]
    assert call_offsets == [0, PAGE_SIZE]


def test_fetch_stops_at_limit_even_with_full_page(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    page1 = [{"id": str(i)} for i in range(PAGE_SIZE)]
    session.get.side_effect = [_mock_response(json_payload=page1)]

    fetcher = _make_fetcher(session)
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=500)

    assert len(out) == 500
    # Only one call: $limit was clamped to 500 (under PAGE_SIZE), short page logic ends loop.
    assert session.get.call_count == 1
    assert session.get.call_args.kwargs["params"]["$limit"] == 500


def test_fetch_zero_limit_returns_empty(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=0)
    assert out == []
    session.get.assert_not_called()


def test_fetch_empty_first_page_terminates(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=[])
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=5000)
    assert out == []
    assert session.get.call_count == 1


# ---------------------------------------------------------------------------
# Retry / backoff
# ---------------------------------------------------------------------------


def test_fetch_retries_on_429_then_succeeds(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=429, reason="Too Many Requests"),
        _mock_response(json_payload=[{"id": "1"}]),
    ]
    sleeps: list[float] = []
    fetcher = _make_fetcher(session, sleeps=sleeps)
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)
    assert out == [{"id": "1"}]
    assert session.get.call_count == 2
    assert len(sleeps) == 1


def test_fetch_honors_retry_after_header(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=429, headers={"Retry-After": "5"}),
        _mock_response(json_payload=[]),
    ]
    sleeps: list[float] = []
    fetcher = _make_fetcher(session, sleeps=sleeps)
    fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)
    assert sleeps == [5.0]


def test_fetch_retries_on_503_with_exponential_backoff(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=503, reason="Service Unavailable"),
        _mock_response(status=503, reason="Service Unavailable"),
        _mock_response(json_payload=[{"id": "1"}]),
    ]
    sleeps: list[float] = []
    fetcher = SocrataFetcher(
        session=session,
        sleep=lambda s: sleeps.append(s),
        max_retries=4,
        initial_backoff=1.0,
        backoff_factor=2.0,
    )
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)
    assert out == [{"id": "1"}]
    # First retry: 1s; second retry: 2s.
    assert sleeps == [1.0, 2.0]


def test_fetch_raises_after_exhausting_retries(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=503),
        _mock_response(status=503),
        _mock_response(status=503),
    ]
    fetcher = _make_fetcher(session)  # max_retries=3
    with pytest.raises(SocrataHTTPError, match="503"):
        fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)


def test_fetch_4xx_other_than_429_fails_fast(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(status=400, reason="Bad Request", text="bad soql")
    fetcher = _make_fetcher(session)
    with pytest.raises(SocrataHTTPError, match="400"):
        fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)
    assert session.get.call_count == 1


def test_fetch_handles_request_exception_with_retry(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        requests.ConnectionError("connection reset"),
        _mock_response(json_payload=[{"id": "1"}]),
    ]
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)
    assert out == [{"id": "1"}]


def test_fetch_rejects_non_json_content_type(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(
        json_payload=[], content_type="text/html"
    )
    fetcher = _make_fetcher(session)
    with pytest.raises(SocrataHTTPError, match="non-JSON"):
        fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)


def test_fetch_rejects_non_list_payload(chicago_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload={"error": "nope"})
    fetcher = _make_fetcher(session)
    with pytest.raises(SocrataHTTPError, match="Expected JSON list"):
        fetcher.fetch(chicago_source, "2026-04-01", "2026-04-30", limit=10)


# ---------------------------------------------------------------------------
# Provider check
# ---------------------------------------------------------------------------


def test_fetch_rejects_non_socrata_source():
    arcgis_source = SourceSpec(
        source_id="x", display_name="x", provider="arcgis",
        dataset_id="abc", base_url="https://example/", date_field="d", field_map={},
    )
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    fetcher = _make_fetcher(session)
    with pytest.raises(ValueError, match="cannot fetch provider"):
        fetcher.fetch(arcgis_source, "2026-04-01", "2026-04-30", limit=10)
