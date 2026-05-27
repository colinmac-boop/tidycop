"""Platform-specific fetchers and dispatch."""

from __future__ import annotations

from typing import Callable

from tidycop.platform.arcgis import ArcGISFetcher
from tidycop.platform.base import BaseFetcher
from tidycop.platform.ckan import CKANFetcher
from tidycop.platform.socrata import SocrataFetcher

__all__ = [
    "ArcGISFetcher",
    "BaseFetcher",
    "CKANFetcher",
    "SocrataFetcher",
    "get_fetcher",
    "register_fetcher",
]


# Provider → factory callable that returns a fresh BaseFetcher instance.
# Using factories (not pre-instantiated objects) so each call can carry its
# own session / token / retry config if a caller passes one in later.
_REGISTRY: dict[str, Callable[[], BaseFetcher]] = {
    "socrata": SocrataFetcher,
    "arcgis": ArcGISFetcher,
    "ckan": CKANFetcher,
}


def register_fetcher(provider: str, factory: Callable[[], BaseFetcher]) -> None:
    """Register or override a fetcher factory for a provider name."""
    _REGISTRY[provider] = factory


def get_fetcher(provider: str) -> BaseFetcher:
    """Instantiate the fetcher registered for ``provider``.

    Raises:
        NotImplementedError: if no fetcher is registered for the provider.
            (ArcGIS and CKAN raise this until their Day 6/7 ports land.)
    """
    try:
        factory = _REGISTRY[provider]
    except KeyError as e:
        raise NotImplementedError(
            f"no fetcher registered for provider {provider!r}; "
            f"known providers: {sorted(_REGISTRY)}"
        ) from e
    return factory()
