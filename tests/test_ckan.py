"""Unit tests for CKANFetcher.

No network calls — all HTTP responses are mocked. Live smoke test lives in
test_ckan_live.py (opt-in via TIDYCOP_LIVE_CKAN=1).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from tidycop.platform.ckan import (
    PAGE_SIZE,
    CKANFetcher,
    CKANHTTPError,
    _build_sql,
    _build_where,
    _quote_ident,
)
from tidycop.registry import SourceSpec

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pittsburgh_source() -> SourceSpec:
    return SourceSpec(
        source_id="pittsburgh_monthly_criminal_activity",
        display_name="Monthly Criminal Activity",
        provider="ckan",
        dataset_id="bd41992a-987a-4cca-8798-fbe1cd946b07",
        base_url="https://data.wprdc.org",
        date_field="ReportedDate",
        field_map={"std_incident_id": "Report_Number"},
        extras={
            "ckan_date_field_type": "date",
            "order_by": '"ReportedDate" DESC',
        },
    )


def _mock_response(
    *,
    status: int = 200,
    json_payload: Any = None,
    content_type: str = "application/json",
    reason: str = "OK",
    text: str = "",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status
    resp.reason = reason
    resp.headers = {"Content-Type": content_type, **(headers or {})}
    resp.text = text or (str(json_payload) if json_payload is not None else "")
    resp.url = "https://example/mock"
    resp.json.return_value = json_payload
    return resp


def _ok_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {"success": True, "result": {"records": records}}


def _make_fetcher(session: MagicMock, sleeps: list[float] | None = None) -> CKANFetcher:
    sleeps = sleeps if sleeps is not None else []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    return CKANFetcher(session=session, sleep=fake_sleep, max_retries=3, initial_backoff=0.01)


# ---------------------------------------------------------------------------
# _quote_ident
# ---------------------------------------------------------------------------


def test_quote_ident_basic():
    assert _quote_ident("ReportedDate") == '"ReportedDate"'


def test_quote_ident_escapes_double_quote():
    assert _quote_ident('weird"name') == '"weird""name"'


# ---------------------------------------------------------------------------
# _build_where
# ---------------------------------------------------------------------------


def test_build_where_date_type():
    where = _build_where("ReportedDate", date(2026, 4, 1), date(2026, 4, 30), "date")
    assert where == "\"ReportedDate\" >= '2026-04-01' AND \"ReportedDate\" < '2026-05-01'"


def test_build_where_text_type_uses_plain_dates():
    where = _build_where("Report_Date", date(2026, 4, 1), date(2026, 4, 30), "text")
    assert "Report_Date" in where
    assert "00:00:00" not in where
    assert "'2026-04-01'" in where


def test_build_where_datetime_type_includes_time():
    where = _build_where("dt", date(2026, 4, 1), date(2026, 4, 30), "datetime")
    assert "'2026-04-01 00:00:00'" in where
    assert "'2026-05-01 00:00:00'" in where


def test_build_where_single_day_is_one_full_day():
    where = _build_where("ReportedDate", date(2026, 4, 15), date(2026, 4, 15), "date")
    assert "'2026-04-15'" in where
    assert "'2026-04-16'" in where


def test_build_where_rejects_inverted_range():
    with pytest.raises(ValueError):
        _build_where("d", date(2026, 4, 30), date(2026, 4, 1), "date")


def test_build_where_rejects_unknown_field_type():
    with pytest.raises(ValueError, match="unsupported ckan_date_field_type"):
        _build_where("d", date(2026, 4, 1), date(2026, 4, 30), "epoch")


# ---------------------------------------------------------------------------
# _build_sql
# ---------------------------------------------------------------------------


def test_build_sql_with_order_by():
    sql = _build_sql("bd41992a", "\"ReportedDate\" >= '2026-04-01'", '"ReportedDate" DESC', 100, 0)
    assert sql == (
        'SELECT * FROM "bd41992a" '
        "WHERE \"ReportedDate\" >= '2026-04-01' "
        'ORDER BY "ReportedDate" DESC '
        "LIMIT 100 OFFSET 0"
    )


def test_build_sql_without_order_by():
    sql = _build_sql("res", "1=1", None, 50, 10)
    assert "ORDER BY" not in sql
    assert "LIMIT 50 OFFSET 10" in sql


def test_build_sql_quotes_resource_id_with_hyphens():
    sql = _build_sql("bd41992a-987a-4cca-8798-fbe1cd946b07", "1=1", None, 10, 0)
    assert 'FROM "bd41992a-987a-4cca-8798-fbe1cd946b07"' in sql


# ---------------------------------------------------------------------------
# Single-page fetch
# ---------------------------------------------------------------------------


def test_fetch_happy_path_single_page(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    rows = [{"Report_Number": "PGHP24000001"}, {"Report_Number": "PGHP24000002"}]
    session.get.return_value = _mock_response(json_payload=_ok_payload(rows))

    fetcher = _make_fetcher(session)
    out = fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-30", limit=100)

    assert out == rows
    session.get.assert_called_once()
    args, kwargs = session.get.call_args
    assert args[0].endswith("/api/3/action/datastore_search_sql")
    sql = kwargs["params"]["sql"]
    assert 'FROM "bd41992a-987a-4cca-8798-fbe1cd946b07"' in sql
    assert "\"ReportedDate\" >= '2026-04-01'" in sql
    assert "\"ReportedDate\" < '2026-05-01'" in sql
    assert 'ORDER BY "ReportedDate" DESC' in sql
    assert "LIMIT 100 OFFSET 0" in sql


def test_fetch_attaches_api_key_when_set(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=_ok_payload([]))
    CKANFetcher(session=session, api_key="ckan-key-1", sleep=lambda s: None)
    assert session.headers["Authorization"] == "ckan-key-1"


def test_fetch_no_api_key_when_unset(pittsburgh_source, monkeypatch):
    monkeypatch.delenv("CKAN_API_KEY", raising=False)
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    CKANFetcher(session=session, sleep=lambda s: None)
    assert "Authorization" not in session.headers


def test_fetch_sets_user_agent_and_accepts_json(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    _make_fetcher(session)
    assert session.headers["User-Agent"].startswith("tidycop/")
    assert session.headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# Paging
# ---------------------------------------------------------------------------


def test_fetch_pages_until_short_page(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    page1 = [{"Report_Number": str(i)} for i in range(PAGE_SIZE)]
    page2 = [{"Report_Number": str(i)} for i in range(PAGE_SIZE, PAGE_SIZE + 3)]
    session.get.side_effect = [
        _mock_response(json_payload=_ok_payload(page1)),
        _mock_response(json_payload=_ok_payload(page2)),
    ]
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-30", limit=50_000)
    assert len(out) == PAGE_SIZE + 3
    offsets = [
        int(c.kwargs["params"]["sql"].split("OFFSET")[-1].strip())
        for c in session.get.call_args_list
    ]
    assert offsets == [0, PAGE_SIZE]


def test_fetch_stops_at_limit(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    page = [{"Report_Number": str(i)} for i in range(PAGE_SIZE)]
    session.get.side_effect = [_mock_response(json_payload=_ok_payload(page))]
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-30", limit=200)
    assert len(out) == 200
    assert session.get.call_count == 1
    assert "LIMIT 200 OFFSET 0" in session.get.call_args.kwargs["params"]["sql"]


def test_fetch_zero_limit_returns_empty(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    fetcher = _make_fetcher(session)
    assert fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-30", limit=0) == []
    session.get.assert_not_called()


def test_fetch_empty_records_terminates(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=_ok_payload([]))
    fetcher = _make_fetcher(session)
    assert fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-30", limit=10_000) == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_fetch_surfaces_ckan_error_envelope(pittsburgh_source):
    """HTTP 200 with body {success: false, error: {...}} is still a failure."""
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(
        json_payload={
            "success": False,
            "error": {
                "__type": "Validation Error",
                "message": "syntax error at or near 'FROMM'",
            },
        }
    )
    fetcher = _make_fetcher(session)
    with pytest.raises(CKANHTTPError, match="Validation Error"):
        fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_retries_on_503(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=503),
        _mock_response(json_payload=_ok_payload([{"Report_Number": "1"}])),
    ]
    sleeps: list[float] = []
    fetcher = _make_fetcher(session, sleeps=sleeps)
    out = fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-02", limit=10)
    assert out == [{"Report_Number": "1"}]
    assert len(sleeps) == 1


def test_fetch_honors_retry_after_header(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=429, headers={"Retry-After": "3"}),
        _mock_response(json_payload=_ok_payload([])),
    ]
    sleeps: list[float] = []
    fetcher = _make_fetcher(session, sleeps=sleeps)
    fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-02", limit=10)
    assert sleeps == [3.0]


def test_fetch_4xx_other_than_429_fails_fast(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(status=400, reason="Bad Request")
    fetcher = _make_fetcher(session)
    with pytest.raises(CKANHTTPError, match="400"):
        fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_rejects_non_json_content_type(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload={}, content_type="text/html")
    fetcher = _make_fetcher(session)
    with pytest.raises(CKANHTTPError, match="non-JSON"):
        fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_rejects_non_dict_payload(pittsburgh_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=["nope"])
    fetcher = _make_fetcher(session)
    with pytest.raises(CKANHTTPError, match="Expected JSON object"):
        fetcher.fetch(pittsburgh_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_rejects_non_ckan_source():
    src = SourceSpec(
        source_id="x",
        display_name="x",
        provider="socrata",
        dataset_id="d",
        base_url="https://example/",
        date_field="d",
        field_map={},
    )
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    fetcher = _make_fetcher(session)
    with pytest.raises(ValueError, match="cannot fetch provider"):
        fetcher.fetch(src, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_requires_dataset_id():
    src = SourceSpec(
        source_id="x",
        display_name="x",
        provider="ckan",
        dataset_id="",
        base_url="https://example/",
        date_field="d",
        field_map={},
    )
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    fetcher = _make_fetcher(session)
    with pytest.raises(ValueError, match="missing dataset_id"):
        fetcher.fetch(src, "2026-04-01", "2026-04-02", limit=10)
