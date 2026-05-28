"""Tests for tidycop.registry."""

from __future__ import annotations

from datetime import date

import pytest

from tidycop import registry as reg
from tidycop.registry import (
    CitySpec,
    SourceSpec,
    get_city_spec,
    list_supported_cities,
    load_registry,
    normalize_city_key,
)

MVP_CITIES = {"chicago", "seattle", "san_francisco", "detroit", "pittsburgh"}


@pytest.fixture(autouse=True)
def _clear_cache():
    """Make sure each test sees a fresh registry load."""
    reg._reset_cache()
    yield
    reg._reset_cache()


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_load_registry_has_all_mvp_cities():
    registry = load_registry()
    assert MVP_CITIES.issubset(registry.keys())


def test_city_spec_shape():
    spec = get_city_spec("chicago")
    assert isinstance(spec, CitySpec)
    assert spec.city == "chicago"
    assert spec.display_name == "Chicago"
    assert spec.timezone == "America/Chicago"
    assert len(spec.sources) >= 1


def test_source_spec_shape():
    src = get_city_spec("chicago").sources[0]
    assert isinstance(src, SourceSpec)
    assert src.provider == "socrata"
    assert src.dataset_id == "ijzp-q8t2"
    assert src.base_url.endswith("ijzp-q8t2.json")
    assert src.date_field == "date"
    assert src.field_map["std_incident_id"] == "id"


def test_active_from_parsed_as_date():
    seattle_src = get_city_spec("seattle").sources[0]
    assert seattle_src.active_from == date(2008, 1, 1)
    assert seattle_src.active_to is None


def test_arcgis_extras_carried_through():
    detroit_src = get_city_spec("detroit").sources[0]
    assert detroit_src.provider == "arcgis"
    # Provider-specific fields live in `extras`, not on the dataclass proper.
    assert detroit_src.extras["arcgis_date_field_type"] == "date"
    assert detroit_src.extras["object_id_field"] == "ESRI_OID"
    assert detroit_src.extras["return_geometry"] is False


def test_ckan_extras_carried_through():
    pgh_src = get_city_spec("pittsburgh").sources[0]
    assert pgh_src.provider == "ckan"
    assert pgh_src.extras["ckan_date_field_type"] == "date"
    assert "ReportedDate" in pgh_src.extras["order_by"]


def test_coalesce_fallback_field_map_preserved_as_list():
    """Detroit's std_source_record_id is a 3-way fallback."""
    fm = get_city_spec("detroit").sources[0].field_map
    assert fm["std_source_record_id"] == ["incident_entry_id", "crime_id", "ESRI_OID"]


# ---------------------------------------------------------------------------
# Alias resolution
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "input_key,expected",
    [
        ("chicago", "chicago"),
        ("Chicago", "chicago"),
        ("  CHICAGO  ", "chicago"),
        ("sf", "san_francisco"),
        ("SF", "san_francisco"),
        ("san_francisco", "san_francisco"),
        ("san-francisco", "san_francisco"),
        ("san francisco", "san_francisco"),
        ("detroit_mi", "detroit"),
        ("pgh", "pittsburgh"),
        ("pittsburgh_pa", "pittsburgh"),
    ],
)
def test_normalize_city_key(input_key, expected):
    assert normalize_city_key(input_key) == expected


def test_normalize_city_key_unknown():
    with pytest.raises(KeyError):
        normalize_city_key("atlantis")


def test_normalize_city_key_empty():
    with pytest.raises(KeyError):
        normalize_city_key("")


def test_get_city_spec_via_alias():
    assert get_city_spec("sf").city == "san_francisco"
    assert get_city_spec("pgh").city == "pittsburgh"


# ---------------------------------------------------------------------------
# list_supported_cities
# ---------------------------------------------------------------------------


def test_list_supported_cities_shape():
    cities = list_supported_cities()
    # Registry grew past the MVP-5 in v0.2.x; assert MVP is a subset only.
    assert len(cities) >= len(MVP_CITIES)
    keys = {c["city"] for c in cities}
    assert MVP_CITIES.issubset(keys)
    for c in cities:
        assert set(c.keys()) >= {
            "city",
            "display_name",
            "timezone",
            "aliases",
            "providers",
            "source_count",
        }


def test_list_supported_cities_providers():
    by_key = {c["city"]: c for c in list_supported_cities()}
    assert by_key["chicago"]["providers"] == ["socrata"]
    assert by_key["seattle"]["providers"] == ["socrata"]
    assert by_key["san_francisco"]["providers"] == ["socrata"]
    assert by_key["detroit"]["providers"] == ["arcgis"]
    assert by_key["pittsburgh"]["providers"] == ["ckan"]
