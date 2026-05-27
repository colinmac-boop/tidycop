"""Unit tests for ArcGISFetcher.

No network calls — all HTTP responses are mocked. Live smoke test lives in
test_arcgis_live.py (opt-in via TIDYCOP_LIVE_ARCGIS=1).
"""

from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import MagicMock

import pytest
import requests

from tidycop.platform.arcgis import (
    PAGE_SIZE,
    ArcGISFetcher,
    ArcGISHTTPError,
    _build_where,
    _flatten_feature,
)
from tidycop.registry import SourceSpec


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def detroit_source() -> SourceSpec:
    return SourceSpec(
        source_id="detroit_rms_crime_incidents",
        display_name="Detroit RMS Crime Incidents",
        provider="arcgis",
        dataset_id="8e532daeec1149879bd5e67fdd9c8be0",
        base_url="https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/RMS_Crime_Incidents/FeatureServer/0",
        date_field="incident_occurred_at",
        field_map={"std_incident_id": "report_number"},
        extras={
            "arcgis_date_field_type": "date",
            "object_id_field": "ESRI_OID",
            "order_by": "ESRI_OID DESC",
            "return_geometry": False,
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


def _make_fetcher(session: MagicMock, sleeps: list[float] | None = None) -> ArcGISFetcher:
    sleeps = sleeps if sleeps is not None else []

    def fake_sleep(s: float) -> None:
        sleeps.append(s)

    return ArcGISFetcher(session=session, sleep=fake_sleep, max_retries=3, initial_backoff=0.01)


def _features(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"features": [{"attributes": r} for r in rows]}


# ---------------------------------------------------------------------------
# _build_where
# ---------------------------------------------------------------------------


def test_build_where_date_type_uses_timestamp_literal():
    where = _build_where("incident_occurred_at", date(2026, 4, 1), date(2026, 4, 30), "date")
    assert "TIMESTAMP '2026-04-01 00:00:00'" in where
    assert "TIMESTAMP '2026-05-01 00:00:00'" in where
    assert " >= " in where and " < " in where


def test_build_where_string_type_uses_plain_quotes():
    where = _build_where("date_str", date(2026, 4, 1), date(2026, 4, 30), "string")
    assert "TIMESTAMP" not in where
    assert "'2026-04-01'" in where
    assert "'2026-05-01'" in where


def test_build_where_single_day_is_one_full_day():
    where = _build_where("incident_occurred_at", date(2026, 4, 15), date(2026, 4, 15), "date")
    assert "TIMESTAMP '2026-04-15 00:00:00'" in where
    assert "TIMESTAMP '2026-04-16 00:00:00'" in where


def test_build_where_rejects_inverted_range():
    with pytest.raises(ValueError):
        _build_where("d", date(2026, 4, 30), date(2026, 4, 1), "date")


def test_build_where_rejects_unknown_field_type():
    with pytest.raises(ValueError, match="unsupported arcgis_date_field_type"):
        _build_where("d", date(2026, 4, 1), date(2026, 4, 30), "epoch")


# ---------------------------------------------------------------------------
# _flatten_feature
# ---------------------------------------------------------------------------


def test_flatten_feature_attributes_only():
    feat = {"attributes": {"a": 1, "b": 2}}
    assert _flatten_feature(feat, want_geometry=False) == {"a": 1, "b": 2}


def test_flatten_feature_promotes_geometry_when_requested():
    feat = {"attributes": {"a": 1}, "geometry": {"x": -83.1, "y": 42.4}}
    assert _flatten_feature(feat, want_geometry=True) == {
        "a": 1,
        "geometry_x": -83.1,
        "geometry_y": 42.4,
    }


def test_flatten_feature_ignores_geometry_when_not_requested():
    feat = {"attributes": {"a": 1}, "geometry": {"x": -83.1, "y": 42.4}}
    assert _flatten_feature(feat, want_geometry=False) == {"a": 1}


def test_flatten_feature_does_not_clobber_existing_geometry_keys():
    feat = {
        "attributes": {"geometry_x": "pre-existing"},
        "geometry": {"x": -83.1, "y": 42.4},
    }
    out = _flatten_feature(feat, want_geometry=True)
    assert out["geometry_x"] == "pre-existing"
    assert out["geometry_y"] == 42.4


# ---------------------------------------------------------------------------
# Single-page fetch
# ---------------------------------------------------------------------------


def test_fetch_happy_path_single_page(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    rows = [{"report_number": "1701020001"}, {"report_number": "1701020002"}]
    session.get.return_value = _mock_response(json_payload=_features(*rows))

    fetcher = _make_fetcher(session)
    out = fetcher.fetch(detroit_source, "2026-04-01", "2026-04-30", limit=100)

    assert out == rows
    session.get.assert_called_once()
    args, kwargs = session.get.call_args
    # Endpoint must be base_url + /query.
    assert args[0].endswith("/FeatureServer/0/query")
    params = kwargs["params"]
    assert params["f"] == "json"
    assert params["outFields"] == "*"
    assert params["returnGeometry"] == "false"
    assert params["resultRecordCount"] == 100
    assert params["resultOffset"] == 0
    assert "TIMESTAMP '2026-04-01 00:00:00'" in params["where"]


def test_fetch_uses_explicit_order_by_from_extras(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=_features())
    fetcher = _make_fetcher(session)
    fetcher.fetch(detroit_source, "2026-04-01", "2026-04-30", limit=10)
    assert session.get.call_args.kwargs["params"]["orderByFields"] == "ESRI_OID DESC"


def test_fetch_falls_back_to_object_id_field_when_no_order_by():
    src = SourceSpec(
        source_id="x", display_name="x", provider="arcgis", dataset_id="d",
        base_url="https://example/Layer/0", date_field="dt",
        field_map={}, extras={"arcgis_date_field_type": "date", "object_id_field": "MY_OID"},
    )
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=_features())
    fetcher = _make_fetcher(session)
    fetcher.fetch(src, "2026-04-01", "2026-04-02", limit=10)
    assert session.get.call_args.kwargs["params"]["orderByFields"] == "MY_OID ASC"


def test_fetch_sets_geometry_params_when_requested():
    src = SourceSpec(
        source_id="x", display_name="x", provider="arcgis", dataset_id="d",
        base_url="https://example/Layer/0", date_field="dt", field_map={},
        extras={"arcgis_date_field_type": "date", "return_geometry": True},
    )
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(
        json_payload={
            "features": [
                {"attributes": {"id": 1}, "geometry": {"x": -83.1, "y": 42.4}},
            ]
        }
    )
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(src, "2026-04-01", "2026-04-02", limit=10)
    params = session.get.call_args.kwargs["params"]
    assert params["returnGeometry"] == "true"
    assert params["outSR"] == 4326
    # Geometry promoted into the row.
    assert out[0] == {"id": 1, "geometry_x": -83.1, "geometry_y": 42.4}


def test_fetch_attaches_token_when_set(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=_features())
    fetcher = ArcGISFetcher(session=session, token="tok-xyz", sleep=lambda s: None)
    fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)
    assert session.get.call_args.kwargs["params"]["token"] == "tok-xyz"


def test_fetch_no_token_when_unset(detroit_source, monkeypatch):
    monkeypatch.delenv("ARCGIS_TOKEN", raising=False)
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=_features())
    fetcher = ArcGISFetcher(session=session, sleep=lambda s: None)
    fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)
    assert "token" not in session.get.call_args.kwargs["params"]


# ---------------------------------------------------------------------------
# Paging
# ---------------------------------------------------------------------------


def test_fetch_pages_until_short_page(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    page1 = _features(*[{"report_number": str(i)} for i in range(PAGE_SIZE)])
    page1["exceededTransferLimit"] = True
    page2 = _features(*[{"report_number": str(i)} for i in range(PAGE_SIZE, PAGE_SIZE + 5)])
    session.get.side_effect = [
        _mock_response(json_payload=page1),
        _mock_response(json_payload=page2),
    ]
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(detroit_source, "2026-04-01", "2026-04-30", limit=10_000)
    assert len(out) == PAGE_SIZE + 5
    offsets = [c.kwargs["params"]["resultOffset"] for c in session.get.call_args_list]
    assert offsets == [0, PAGE_SIZE]


def test_fetch_terminates_when_server_clears_exceeded_flag(detroit_source):
    """exceededTransferLimit=False is the server's 'no more data' signal."""
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    page1 = _features(*[{"report_number": str(i)} for i in range(PAGE_SIZE)])
    page1["exceededTransferLimit"] = False  # full page, but no more after this
    session.get.return_value = _mock_response(json_payload=page1)
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(detroit_source, "2026-04-01", "2026-04-30", limit=10_000)
    assert len(out) == PAGE_SIZE
    assert session.get.call_count == 1


def test_fetch_stops_at_limit(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    page = _features(*[{"report_number": str(i)} for i in range(PAGE_SIZE)])
    session.get.side_effect = [_mock_response(json_payload=page)]
    fetcher = _make_fetcher(session)
    out = fetcher.fetch(detroit_source, "2026-04-01", "2026-04-30", limit=500)
    assert len(out) == 500
    assert session.get.call_count == 1
    assert session.get.call_args.kwargs["params"]["resultRecordCount"] == 500


def test_fetch_zero_limit_returns_empty(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    fetcher = _make_fetcher(session)
    assert fetcher.fetch(detroit_source, "2026-04-01", "2026-04-30", limit=0) == []
    session.get.assert_not_called()


def test_fetch_empty_features_terminates(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload={"features": []})
    fetcher = _make_fetcher(session)
    assert fetcher.fetch(detroit_source, "2026-04-01", "2026-04-30", limit=10_000) == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_fetch_surfaces_arcgis_error_envelope(detroit_source):
    """HTTP 200 with body {error:{...}} is still a failure."""
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(
        json_payload={
            "error": {
                "code": 400,
                "message": "Unable to perform query.",
                "details": ["Invalid where clause"],
            }
        }
    )
    fetcher = _make_fetcher(session)
    with pytest.raises(ArcGISHTTPError, match="Unable to perform query"):
        fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_retries_on_503(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=503),
        _mock_response(json_payload=_features({"report_number": "1"})),
    ]
    sleeps: list[float] = []
    fetcher = _make_fetcher(session, sleeps=sleeps)
    out = fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)
    assert out == [{"report_number": "1"}]
    assert len(sleeps) == 1


def test_fetch_honors_retry_after_header(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.side_effect = [
        _mock_response(status=429, headers={"Retry-After": "4"}),
        _mock_response(json_payload=_features()),
    ]
    sleeps: list[float] = []
    fetcher = _make_fetcher(session, sleeps=sleeps)
    fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)
    assert sleeps == [4.0]


def test_fetch_4xx_other_than_429_fails_fast(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(status=400, reason="Bad Request")
    fetcher = _make_fetcher(session)
    with pytest.raises(ArcGISHTTPError, match="400"):
        fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_rejects_non_json_content_type(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload={}, content_type="text/html")
    fetcher = _make_fetcher(session)
    with pytest.raises(ArcGISHTTPError, match="non-JSON"):
        fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_rejects_non_dict_payload(detroit_source):
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.get.return_value = _mock_response(json_payload=["nope"])
    fetcher = _make_fetcher(session)
    with pytest.raises(ArcGISHTTPError, match="Expected JSON object"):
        fetcher.fetch(detroit_source, "2026-04-01", "2026-04-02", limit=10)


def test_fetch_rejects_non_arcgis_source():
    src = SourceSpec(
        source_id="x", display_name="x", provider="socrata", dataset_id="d",
        base_url="https://example/", date_field="d", field_map={},
    )
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    fetcher = _make_fetcher(session)
    with pytest.raises(ValueError, match="cannot fetch provider"):
        fetcher.fetch(src, "2026-04-01", "2026-04-02", limit=10)
