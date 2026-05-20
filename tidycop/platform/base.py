"""Base fetcher interface."""

from abc import ABC, abstractmethod
from datetime import date
from typing import Any


class BaseFetcher(ABC):
    """Abstract base for platform fetchers."""
    
    @abstractmethod
    def fetch(
        self,
        spec: dict[str, Any],
        start_date: date,
        end_date: date,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Fetch raw records from platform."""
        pass
