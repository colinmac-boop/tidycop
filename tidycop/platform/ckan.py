"""CKAN datastore fetcher.

CKAN exposes datasets through ``/api/3/action/datastore_search_sql``, which
accepts a single ``sql`` query parameter. Identifiers (resource_id and
column names) are SQL identifiers — wrapped in double quotes, with literal
quotes escaped by doubling.

Used by Pittsburgh (WPRDC) and San Antonio. Reference:
  - https://docs.ckan.org/en/latest/maintaining/datastore.html

Behavior (ported from tidycops R ``fetch_ckan_dataset``):
  - SQL shape:
        SELECT * FROM "<resource_id>"
        WHERE <field> >= 'YYYY-MM-DD' AND <field> < 'YYYY-MM-DD+1'
        ORDER BY <order_by>
        LIMIT n OFFSET m
  - Date WHERE uses string literals; ``ckan_date_field_type`` of "datetime"
    appends ``00:00:00`` (matches R), "date" and "text" use plain dates.
  - Page size up to 10000 (CKAN's default cap).
  - Terminate on short page, empty records, or overall limit reached.
  - CKAN error envelope: HTTP 200 with ``{"success": false, ...}`` body.
    Treated as failure with code+message surfaced.
  - Retry/backoff: 429/5xx, Retry-After honored. Same shape as Socrata/ArcGIS.
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

USER_AGENT = "tidycop/0.3.0 (+https://citycrimemap.us)"
PAGE_SIZE = 10_000
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


def _quote_ident(name: str) -> str:
    """Escape a SQL identifier per CKAN/PostgreSQL conventions."""
    return '"' + name.replace('"', '""') + '"'


def _build_where(date_field: str, start: date, end: date, field_type: str) -> str:
    """Compose the CKAN SQL ``WHERE`` clause for an inclusive day range.

    end is treated as exclusive at midnight of (end+1). ``field_type``:
      - "date" / "text" → plain 'YYYY-MM-DD'
      - "datetime"      → 'YYYY-MM-DD HH:MM:SS'
    """
    if end < start:
        raise ValueError(f"end_date ({end}) is before start_date ({start})")
    end_exclusive = end + timedelta(days=1)
    field_sql = _quote_ident(date_field)
    if field_type == "datetime":
        start_s = f"{start.isoformat()} 00:00:00"
        end_s = f"{end_exclusive.isoformat()} 00:00:00"
    elif field_type in ("date", "text"):
        start_s = start.isoformat()
        end_s = end_exclusive.isoformat()
    else:
        raise ValueError(
            f"unsupported ckan_date_field_type={field_type!r}; "
            "expected 'date', 'datetime', or 'text'"
        )
    return f"{field_sql} >= '{start_s}' AND {field_sql} < '{end_s}'"


def _build_sql(resource_id: str, where: str, order_by: str | None, limit: int, offset: int) -> str:
    parts = [
        f"SELECT * FROM {_quote_ident(resource_id)}",
        f"WHERE {where}",
    ]
    if order_by:
        parts.append(f"ORDER BY {order_by}")
    parts.append(f"LIMIT {int(limit)} OFFSET {int(offset)}")
    return " ".join(parts)


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


class CKANHTTPError(RuntimeError):
    """Raised when CKAN returns an unrecoverable HTTP or API error."""


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


class CKANFetcher(BaseFetcher):
    """Fetch records from a CKAN datastore via datastore_search_sql."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        sleep: Any = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.api_key = api_key or os.environ.get("CKAN_API_KEY") or None
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.backoff_factor = backoff_factor
        self._sleep = sleep

        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "application/json")
        if self.api_key:
            self.session.headers["Authorization"] = self.api_key

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
        if source.provider != "ckan":
            raise ValueError(f"CKANFetcher cannot fetch provider={source.provider!r}")
        if not source.date_field:
            raise ValueError(f"source {source.source_id!r} missing date_field")
        if not source.dataset_id:
            raise ValueError(f"source {source.source_id!r} missing dataset_id (CKAN resource_id)")
        if limit <= 0:
            return

        start = _coerce_date(start_date)
        end = _coerce_date(end_date)

        field_type = source.extras.get("ckan_date_field_type", "date")
        where = _build_where(source.date_field, start, end, field_type)
        order_by = source.extras.get("order_by") or None

        endpoint = source.base_url.rstrip("/") + "/api/3/action/datastore_search_sql"

        retrieved = 0
        offset = 0
        while retrieved < limit:
            page_limit = min(PAGE_SIZE, limit - retrieved)
            sql = _build_sql(source.dataset_id, where, order_by, page_limit, offset)
            payload = self._get_page(endpoint, {"sql": sql})

            # CKAN error envelope (HTTP 200 with success=false body).
            if not payload.get("success"):
                err = payload.get("error") or {}
                err_type = err.get("__type") or "Unknown"
                err_msg = err.get("message") or payload.get("help") or "no detail"
                raise CKANHTTPError(f"CKAN query failed ({err_type}): {err_msg}")

            result = payload.get("result") or {}
            records = result.get("records") or []
            if not records:
                return

            for rec in records:
                yield rec
                retrieved += 1
                if retrieved >= limit:
                    return

            if len(records) < page_limit:
                return
            offset += len(records)

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
                    "ckan: request error on attempt %d/%d (%s)",
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt >= self.max_retries:
                    raise CKANHTTPError(
                        f"CKAN request failed after {self.max_retries} attempts: {e}"
                    ) from e
                self._sleep(
                    _sleep_for_retry(None, attempt, self.initial_backoff, self.backoff_factor)
                )
                continue

            status = response.status_code
            if 200 <= status < 300:
                ct = response.headers.get("Content-Type", "")
                if "json" not in ct.lower():
                    raise CKANHTTPError(f"CKAN returned non-JSON response (Content-Type={ct!r})")
                payload = response.json()
                if not isinstance(payload, dict):
                    raise CKANHTTPError(f"Expected JSON object, got {type(payload).__name__}")
                return payload

            if status in RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    raise CKANHTTPError(f"CKAN returned {status} after {self.max_retries} attempts")
                delay = _sleep_for_retry(
                    response, attempt, self.initial_backoff, self.backoff_factor
                )
                logger.warning(
                    "ckan: HTTP %d, sleeping %.2fs before retry %d/%d",
                    status,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                self._sleep(delay)
                continue

            body = (response.text or "")[:500]
            raise CKANHTTPError(
                f"CKAN HTTP {status}: {response.reason!r}. URL={response.url} body={body!r}"
            )

        if last_exc:
            raise CKANHTTPError(str(last_exc))
        raise CKANHTTPError("Exhausted retries with no response")
