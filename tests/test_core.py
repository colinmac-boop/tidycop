"""Core functionality tests."""

import pytest


def test_get_incidents_not_implemented():
    """Placeholder until core is ported."""
    from tidycop import get_incidents
    
    with pytest.raises(NotImplementedError):
        get_incidents("chicago", "2026-04-01", "2026-04-30")
