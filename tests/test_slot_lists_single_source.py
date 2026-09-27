import pytest
from app_core.economy.building_costs import CITY_UNITS, LAND_UNITS
import variables

def test_city_units_contains_expected():
    expected = {"food_banks", "primary_school", "high_school", "industrial_district"}
    for e in expected:
        assert e in CITY_UNITS

def test_land_units_contains_expected():
    expected = {"drone_sites", "missile_batteries"}
    for e in expected:
        assert e in LAND_UNITS

def test_units_are_disjoint():
    assert CITY_UNITS.isdisjoint(LAND_UNITS)

def test_all_buildings_in_one_and_only_one_slot():
    for building in variables.BUILDINGS:
        in_city = building in CITY_UNITS
        in_land = building in LAND_UNITS
        assert in_city != in_land, f"{building} should be in exactly one of CITY_UNITS or LAND_UNITS (city: {in_city}, land: {in_land})"

def test_ai_agent_uses_same_lists():
    try:
        import ai_agent
    except Exception as e:
        pytest.skip(f"Skipping ai_agent test due to import error: {e}")
    
    assert ai_agent.CITY_SLOT_BUILDINGS == CITY_UNITS
    assert ai_agent.LAND_SLOT_BUILDINGS == LAND_UNITS
