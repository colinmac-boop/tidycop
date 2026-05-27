"""Core functionality tests (smoke).

Real fetcher tests live alongside each platform implementation.
Day 5 will wire core.get_incidents() to the registry + fetchers.
"""

import pytest


def test_get_incidents_not_implemented():
    """Placeholder until core is wired up (Day 5)."""
    from tidycop import get_incidents

    with pytest.raises(NotImplementedError):
        get_incidents("chicago", "2026-04-01", "2026-04-30")
