"""ArcGIS FeatureServer fetcher.

Esri REST query API — e.g. Detroit RMS Crime Incidents, Boston, Cleveland,
Indianapolis, Rochester. Endpoint pattern is ``<base_url>/query``.

Reference:
  - https://developers.arcgis.com/rest/services-reference/enterprise/query-feature-service-layer.htm

Behavior (ported from tidycops R ``fetch_arcgis_dataset``):
  - ``where`` clause; default ``"1=1"`` if none (ArcGIS rejects empty).
  - Date filter for ``arcgis_date_field_type == "date"``:
        field >= TIMESTAMP 'YYYY-MM-DD 00:00:00' AND
        field <  TIMESTAMP 'YYYY-MM-DD+1 00:00:00'    (end-exclusive)
    For ``"string"`` field types, fall back to plain quoted strings.
  - Paging via ``resultOffset`` + ``resultRecordCount`` (PAGE_SIZE 2000).
  - ``returnGeometry`` configurable per source (default False matches Detroit
    spec). When True, server returns ``geometry: {x, y}``; we flatten to
    ``geometry_x``/``geometry_y`` keys (Rochester relies on this).
  - ``orderByFields`` from source.extras["order_by"]; defaults to OBJECTID DESC.
  - Errors come back as HTTP 200 with ``{"error": {...}}`` in the body —
    treat those as failures and surface code + message.
  - Retry/backoff: same policy as Socrata (429/5xx, Retry-After).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta
from typing import Any, Iterator

import requests

from tidycop.platform.base import BaseFetcher
from tidycop.registry import SourceSpec

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

USER_AGENT = "tidycop/0.1.0 (+https://neighborhoodcrimemap.com)"
PAGE_SIZE = 2000  # Esri default is often 2000; we honor short pages anyway.
DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 4
DEFAULT_INITIAL_BACKOFF = 1.0
DEFAULT_BACKOFF_FACTOR = 2.0
MAX_BACKOFF = 30.0
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _coerce_date(value: date | str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.split("T")[0]).date()
    raise TypeError(f"start_date/end_date must be date or ISO string, got {type(value).__name__}")


def _build_where(date_field: str, start: date, end: date, field_type: str) -> str:
    """Compose the ArcGIS ``where`` clause for an inclusive day range.

    Note on timezones: hosted ArcGIS FeatureServer layers usually interpret
    TIMESTAMP literals in the server's (typically UTC) timezone, not the
    city's local timezone. This means a request for 2026-04-01..2026-04-30
    will include data points whose city-local timestamps fall slightly
    outside that window (e.g. Detroit records stamped 2026-03-31T20:00 EDT,
    which is 2026-04-01T00:00 UTC). The R upstream behaves the same way.
    For day-level analytics that's fine; if exact city-local boundaries
    matter, post-filter on ``std_incident_date`` after normalization.
    """
    if end < start:
        raise ValueError(f"end_date ({end}) is before start_date ({start})")
    end_exclusive = end + timedelta(days=1)
    if field_type == "date":
        # Esri TIMESTAMP literal — preferred for esriFieldTypeDate columns.
        return (
            f"{date_field} >= TIMESTAMP '{start.isoformat()} 00:00:00' AND "
            f"{date_field} <  TIMESTAMP '{end_exclusive.isoformat()} 00:00:00'"
        )
    if field_type == "string":
        return (
            f"{date_field} >= '{start.isoformat()}' AND "
            f"{date_field} <  '{end_exclusive.isoformat()}'"
        )
    raise ValueError(
        f"unsupported arcgis_date_field_type={field_type!r}; expected 'date' or 'string'"
    )


def _sleep_for_retry(
    response: requests.Response | None,
    attempt: int,
    initial_backoff: float,
    backoff_factor: float,
) -> float:
    retry_after: float | None = None
    if response is not None:
        ra = response.headers.get("Retry-After")
        if ra:
            try:
                retry_after = float(ra)
            except ValueError:
                retry_after = None
    if retry_after is None:
        retry_after = initial_backoff * (backoff_factor ** (attempt - 1))
    return min(retry_after, MAX_BACKOFF)


def _flatten_feature(feature: dict[str, Any], *, want_geometry: bool) -> dict[str, Any]:
    """Flatten {attributes:{...}, geometry:{x, y}} into a single dict.

    Promotes geometry to ``geometry_x``/``geometry_y`` (matches the R port,
    which Rochester uses for lat/lon).
    """
    attrs = dict(feature.get("attributes") or {})
    if want_geometry:
        geom = feature.get("geometry") or {}
        if "x" in geom and "geometry_x" not in attrs:
            attrs["geometry_x"] = geom["x"]
        if "y" in geom and "geometry_y" not in attrs:
            attrs["geometry_y"] = geom["y"]
    return attrs


class ArcGISHTTPError(RuntimeError):
    """Raised when ArcGIS returns an unrecoverable HTTP or API error."""


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


class ArcGISFetcher(BaseFetcher):
    """Fetch records from an Esri FeatureServer layer."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        sleep: Any = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.token = token or os.environ.get("ARCGIS_TOKEN") or None
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.backoff_factor = backoff_factor
        self._sleep = sleep

        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "application/json")

    # ---- Public API ------------------------------------------------------

    def fetch(
        self,
        source: SourceSpec,
        start_date: date | str,
        end_date: date | str,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        return list(self.iter_fetch(source, start_date, end_date, limit=limit))

    def iter_fetch(
        self,
        source: SourceSpec,
        start_date: date | str,
        end_date: date | str,
        *,
        limit: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        if source.provider != "arcgis":
            raise ValueError(f"ArcGISFetcher cannot fetch provider={source.provider!r}")
        if not source.date_field:
            raise ValueError(f"source {source.source_id!r} missing date_field")
        if limit <= 0:
            return

        start = _coerce_date(start_date)
        end = _coerce_date(end_date)

        field_type = source.extras.get("arcgis_date_field_type", "date")
        where = _build_where(source.date_field, start, end, field_type)
        order_by = source.extras.get("order_by") or f"{source.extras.get('object_id_field', 'OBJECTID')} ASC"
        return_geometry = bool(source.extras.get("return_geometry", False))

        # Endpoint is <base_url>/query — base_url points at the layer.
        url = source.base_url.rstrip("/") + "/query"

        retrieved = 0
        offset = 0
        while retrieved < limit:
            page_limit = min(PAGE_SIZE, limit - retrieved)
            params: dict[str, Any] = {
                "f": "json",
                "where": where,
                "outFields": "*",
                "returnGeometry": "true" if return_geometry else "false",
                "orderByFields": order_by,
                "resultOffset": offset,
                "resultRecordCount": page_limit,
            }
            if return_geometry:
                params.setdefault("outSR", 4326)
            if self.token:
                params["token"] = self.token

            payload = self._get_page(url, params)

            # ArcGIS error envelope (HTTP 200 with body error).
            if "error" in payload:
                err = payload["error"] or {}
                code = err.get("code", "unknown")
                msg = err.get("message", "Unknown error")
                details = " ".join(d for d in (err.get("details") or []) if d)
                raise ArcGISHTTPError(
                    f"ArcGIS query failed ({code}): {msg}" + (f" {details}" if details else "")
                )

            features = payload.get("features") or []
            if not features:
                return

            for feature in features:
                yield _flatten_feature(feature, want_geometry=return_geometry)
                retrieved += 1
                if retrieved >= limit:
                    return

            # Termination heuristics: short page or server cleared the flag.
            if len(features) < page_limit:
                return
            if "exceededTransferLimit" in payload and not payload["exceededTransferLimit"]:
                return
            offset += len(features)

    # ---- Internals -------------------------------------------------------

    def _get_page(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            response: requests.Response | None = None
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                last_exc = e
                logger.warning(
                    "arcgis: request error on attempt %d/%d (%s)",
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt >= self.max_retries:
                    raise ArcGISHTTPError(
                        f"ArcGIS request failed after {self.max_retries} attempts: {e}"
                    ) from e
                self._sleep(
                    _sleep_for_retry(None, attempt, self.initial_backoff, self.backoff_factor)
                )
                continue

            status = response.status_code
            if 200 <= status < 300:
                ct = response.headers.get("Content-Type", "")
                if "json" not in ct.lower():
                    raise ArcGISHTTPError(
                        f"ArcGIS returned non-JSON response (Content-Type={ct!r})"
                    )
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ArcGISHTTPError(
                        f"Expected JSON object, got {type(payload).__name__}"
                    )
                return payload

            if status in RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    raise ArcGISHTTPError(
                        f"ArcGIS returned {status} after {self.max_retries} attempts"
                    )
                delay = _sleep_for_retry(
                    response, attempt, self.initial_backoff, self.backoff_factor
                )
                logger.warning(
                    "arcgis: HTTP %d, sleeping %.2fs before retry %d/%d",
                    status,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                self._sleep(delay)
                continue

            body = (response.text or "")[:500]
            raise ArcGISHTTPError(
                f"ArcGIS HTTP {status}: {response.reason!r}. URL={response.url} body={body!r}"
            )

        if last_exc:
            raise ArcGISHTTPError(str(last_exc))
        raise ArcGISHTTPError("Exhausted retries with no response")
