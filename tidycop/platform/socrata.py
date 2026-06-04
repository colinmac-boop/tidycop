"""Socrata API fetcher.

Socrata Open Data API (SODA 2.0) datasets — e.g. Chicago `ijzp-q8t2`,
Seattle `tazs-3rd5`, San Francisco `wg3w-h783`.

Reference:
  - https://dev.socrata.com/docs/queries/
  - https://dev.socrata.com/docs/paging.html
  - https://dev.socrata.com/docs/app-tokens.html

Behavior (ported from tidycops R `fetch_socrata_dataset` + `.fetch_with_retry`):
  - Page size 1000 (Socrata default cap without app token; we never exceed).
  - Paged via ``$offset`` until either ``limit`` is reached or the page is short.
  - Date filter: ``date_field >= 'YYYY-MM-DDT00:00:00' AND
                 date_field < '<end+1>T00:00:00'`` (end-exclusive).
  - Ordered by ``date_field ASC`` for stable paging.
  - Retry on 429/500/502/503/504 with exponential backoff; honor Retry-After.
  - 4xx (non-429) fail fast with descriptive errors.
  - Optional app token via env ``SOCRATA_APP_TOKEN`` → ``X-App-Token`` header.
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
PAGE_SIZE = 1000
DEFAULT_TIMEOUT = 30.0  # seconds, per-request
DEFAULT_MAX_RETRIES = 4
DEFAULT_INITIAL_BACKOFF = 1.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0
MAX_BACKOFF = 30.0  # cap a single sleep at 30s
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


def _build_where(date_field: str, start: date, end: date) -> str:
    """Compose the SoQL ``$where`` for an inclusive day range.

    Matches R behavior: end-exclusive at midnight on (end+1), so a full day
    of records on ``end`` is included regardless of intraday timestamps.
    """
    if end < start:
        raise ValueError(f"end_date ({end}) is before start_date ({start})")
    start_s = f"{start.isoformat()}T00:00:00"
    end_exclusive = (end + timedelta(days=1)).isoformat()
    end_s = f"{end_exclusive}T00:00:00"
    return f"{date_field} >= '{start_s}' AND {date_field} < '{end_s}'"


def _sleep_for_retry(
    response: requests.Response | None,
    attempt: int,
    initial_backoff: float,
    backoff_factor: float,
) -> float:
    """Compute backoff seconds, honoring Retry-After when present."""
    retry_after: float | None = None
    if response is not None:
        ra = response.headers.get("Retry-After")
        if ra:
            try:
                retry_after = float(ra)
            except ValueError:
                # HTTP-date form — fall back to exponential.
                retry_after = None
    if retry_after is None:
        retry_after = initial_backoff * (backoff_factor ** (attempt - 1))
    return min(retry_after, MAX_BACKOFF)


class SocrataHTTPError(RuntimeError):
    """Raised when Socrata returns an unrecoverable HTTP error."""


# ---------------------------------------------------------------------------
# Fetcher
# ---------------------------------------------------------------------------


class SocrataFetcher(BaseFetcher):
    """Fetch records from a Socrata-hosted dataset."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        app_token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        initial_backoff: float = DEFAULT_INITIAL_BACKOFF,
        backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
        sleep: Any = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.app_token = app_token or os.environ.get("SOCRATA_APP_TOKEN") or None
        self.timeout = timeout
        self.max_retries = max_retries
        self.initial_backoff = initial_backoff
        self.backoff_factor = backoff_factor
        self._sleep = sleep  # injectable for tests

        self.session.headers.setdefault("User-Agent", USER_AGENT)
        self.session.headers.setdefault("Accept", "application/json")
        if self.app_token:
            self.session.headers["X-App-Token"] = self.app_token

    # ---- Public API ------------------------------------------------------

    def fetch(
        self,
        source: SourceSpec,
        start_date: date | str,
        end_date: date | str,
        *,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Fetch records, page through results, return a single list."""
        return list(self.iter_fetch(source, start_date, end_date, limit=limit))

    def iter_fetch(
        self,
        source: SourceSpec,
        start_date: date | str,
        end_date: date | str,
        *,
        limit: int = 1000,
    ) -> Iterator[dict[str, Any]]:
        """Stream records one at a time across pages."""
        if source.provider != "socrata":
            raise ValueError(f"SocrataFetcher cannot fetch provider={source.provider!r}")
        if not source.date_field:
            raise ValueError(f"source {source.source_id!r} missing date_field")
        if limit <= 0:
            return

        start = _coerce_date(start_date)
        end = _coerce_date(end_date)
        where = _build_where(source.date_field, start, end)

        retrieved = 0
        offset = 0
        while retrieved < limit:
            page_limit = min(PAGE_SIZE, limit - retrieved)
            params = {
                "$where": where,
                "$order": f"{source.date_field} ASC",
                "$limit": page_limit,
                "$offset": offset,
            }
            page = self._get_page(source.base_url, params)
            if not page:
                return
            for rec in page:
                yield rec
                retrieved += 1
                if retrieved >= limit:
                    return
            if len(page) < page_limit:
                # Short page → server has nothing more.
                return
            offset += len(page)

    # ---- Internals -------------------------------------------------------

    def _get_page(self, url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Issue one GET with retry/backoff, return decoded JSON list."""
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            response: requests.Response | None = None
            try:
                response = self.session.get(url, params=params, timeout=self.timeout)
            except requests.RequestException as e:
                last_exc = e
                logger.warning(
                    "socrata: request error on attempt %d/%d (%s)",
                    attempt,
                    self.max_retries,
                    e,
                )
                if attempt >= self.max_retries:
                    raise SocrataHTTPError(
                        f"Socrata request failed after {self.max_retries} attempts: {e}"
                    ) from e
                self._sleep(
                    _sleep_for_retry(None, attempt, self.initial_backoff, self.backoff_factor)
                )
                continue

            status = response.status_code
            if 200 <= status < 300:
                ct = response.headers.get("Content-Type", "")
                if "json" not in ct.lower():
                    raise SocrataHTTPError(
                        f"Socrata returned non-JSON response (Content-Type={ct!r})"
                    )
                payload = response.json()
                if not isinstance(payload, list):
                    raise SocrataHTTPError(f"Expected JSON list, got {type(payload).__name__}")
                return payload

            if status in RETRYABLE_STATUS:
                if attempt >= self.max_retries:
                    raise SocrataHTTPError(
                        f"Socrata returned {status} after {self.max_retries} attempts"
                    )
                delay = _sleep_for_retry(
                    response, attempt, self.initial_backoff, self.backoff_factor
                )
                logger.warning(
                    "socrata: HTTP %d, sleeping %.2fs before retry %d/%d",
                    status,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                self._sleep(delay)
                continue

            # Non-retryable 4xx
            body = (response.text or "")[:500]
            raise SocrataHTTPError(
                f"Socrata HTTP {status}: {response.reason!r}. URL={response.url} body={body!r}"
            )

        # Should be unreachable, but keep mypy happy.
        if last_exc:
            raise SocrataHTTPError(str(last_exc))
        raise SocrataHTTPError("Exhausted retries with no response")
