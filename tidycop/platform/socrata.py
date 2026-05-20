"""Socrata API wrapper."""

from datetime import date
from typing import Any

from tidycop.platform.base import BaseFetcher


class SocrataFetcher(BaseFetcher):
    """Fetcher for Socrata-hosted datasets."""
    
    def fetch(
        self,
        spec: dict[str, Any],
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch from Socrata using $where + paging."""
        raise NotImplementedError("Socrata fetcher port in progress")
