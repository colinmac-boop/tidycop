"""City registry and spec loading."""

from typing import Any


def list_supported_cities() -> list[dict[str, Any]]:
    """List all supported cities with metadata."""
    raise NotImplementedError("Port in progress")


def get_city_spec(city: str) -> dict[str, Any]:
    """Load city specification from registry."""
    raise NotImplementedError("Port in progress")
