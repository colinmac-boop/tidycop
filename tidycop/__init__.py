"""tidycop — City-agnostic interface for public police incident data.

Python port of tidycops (MIT, Anthony Galvan).
"""

__version__ = "0.3.0"

from tidycop.core import get_incidents
from tidycop.registry import (
    get_city_spec,
    list_supported_cities,
    normalize_city_key,
)
from tidycop.schema import STD_COLUMNS

__all__ = [
    "STD_COLUMNS",
    "__version__",
    "get_city_spec",
    "get_incidents",
    "list_supported_cities",
    "normalize_city_key",
]
