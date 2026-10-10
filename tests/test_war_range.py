import pytest

pytestmark = pytest.mark.no_server

from wars.war_range import (
    WAR_RANGE_LOW,
    WAR_RANGE_HIGH,
    UNIT_WEIGHTS,
    war_strength,
    in_war_range,
    war_range_bounds,
    format_war_range_error,
)


def test_war_strength_empty():
    assert war_strength(0, {}) == 0.0
    assert war_strength(None, None) == 0.0


def test_war_strength_population_only():
    # 1,000,000 population / 1000 = 1000.0 strength
    assert war_strength(1_000_000, {}) == 1000.0
    assert war_strength(500, {}) == 0.5


def test_war_strength_units_weights():
    # Verify standard unit weights from spec
    assert UNIT_WEIGHTS["soldiers"] == 1
    assert UNIT_WEIGHTS["tanks"] == 40
    assert UNIT_WEIGHTS["artillery"] == 30
    assert UNIT_WEIGHTS["fighters"] == 60
    assert UNIT_WEIGHTS["bombers"] == 70
    assert UNIT_WEIGHTS["apaches"] == 50
    assert UNIT_WEIGHTS["destroyers"] == 120
    assert UNIT_WEIGHTS["cruisers"] == 200
    assert UNIT_WEIGHTS["submarines"] == 150
    assert UNIT_WEIGHTS["spies"] == 0
    assert UNIT_WEIGHTS["icbms"] == 500
    assert UNIT_WEIGHTS["nukes"] == 2000

    units = {
        "soldiers": 100,      # 100 * 1 = 100
        "tanks": 10,          # 10 * 40 = 400
        "fighters": 5,        # 5 * 60 = 300
        "nukes": 1,           # 1 * 2000 = 2000
        "spies": 50,          # 50 * 0 = 0
    }
    # Total units = 2800.0
    # Population 2,000,000 / 1000 = 2000.0
    # Total = 4800.0
    assert war_strength(2_000_000, units) == 4800.0


def test_war_strength_case_insensitivity():
    units = {"Soldiers": 50, "TANKS": 2}
    # 50 * 1 + 2 * 40 = 130.0
    assert war_strength(0, units) == 130.0


def test_in_war_range_constants():
    assert WAR_RANGE_LOW == 0.75
    assert WAR_RANGE_HIGH == 1.33


def test_in_war_range():
    attacker = 1000.0

    # Boundaries: 750.0 to 1330.0
    assert in_war_range(attacker, 750.0) is True
    assert in_war_range(attacker, 1330.0) is True
    assert in_war_range(attacker, 1000.0) is True

    # Inside range
    assert in_war_range(attacker, 800.0) is True
    assert in_war_range(attacker, 1200.0) is True

    # Outside range
    assert in_war_range(attacker, 749.0) is False
    assert in_war_range(attacker, 1331.0) is False
    assert in_war_range(attacker, 500.0) is False
    assert in_war_range(attacker, 2000.0) is False


def test_in_war_range_zero_strength():
    assert in_war_range(0, 0) is True
    assert in_war_range(0, 10) is False


def test_format_war_range_error():
    msg = format_war_range_error(1000.0)
    assert "750.0" in msg
    assert "1,330.0" in msg
    assert "Your strength: 1,000.0" in msg
