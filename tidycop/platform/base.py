"""Base fetcher interface.

Each platform fetcher (Socrata, ArcGIS, CKAN, ...) implements ``fetch()`` and
returns an iterable of raw JSON-shaped records. Normalization into the std_*
schema happens upstream in ``tidycop.schema.normalize``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any, Iterable

from tidycop.registry import SourceSpec


class BaseFetcher(ABC):
    """Abstract base for platform fetchers."""

    @abstractmethod
    def fetch(
        self,
        source: SourceSpec,
        start_date: date,
        end_date: date,
        *,
        limit: int = 1000,
    ) -> Iterable[dict[str, Any]]:
        """Fetch raw records from the source.

        Args:
            source: SourceSpec for the city/source.
            start_date: Inclusive start date.
            end_date: Inclusive end date.
            limit: Maximum total records to return (overall, not per page).

        Returns:
            An iterable of dict records (one per source row, raw field names).
        """
        raise NotImplementedError
