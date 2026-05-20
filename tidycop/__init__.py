"""tidycop — City-agnostic interface for public police incident data.

Python port of tidycops (MIT, Anthony Galvan).
"""

__version__ = "0.1.0"

from tidycop.core import get_incidents
from tidycop.registry import list_supported_cities

__all__ = ["get_incidents", "list_supported_cities", "__version__"]
