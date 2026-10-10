import pytest

pytestmark = pytest.mark.no_server

from app_core.military.manpower import (
    UNIT_MANPOWER_CREW,
    MANPOWER_SHARE,
    unit_crew_requirement,
    calc_manpower_cap,
    calc_used_manpower,
    calc_free_manpower,
    can_recruit,
    format_manpower_error,
)


def test_crew_weights_match_recruitment_manpower():
    """Crew per unit is the same manpower the recruitment pool charges."""
    from variables import MILDICT

    for name, spec in MILDICT.items():
        assert unit_crew_requirement(name) == int(spec.get("manpower", 0) or 0)
    assert unit_crew_requirement("soldiers") == 1
    assert unit_crew_requirement("nukes") == 0
    assert unit_crew_requirement("unknown_unit") == 0


def test_manpower_cap_calculation():
    """Rule B4: Cap is 10% of working population, fallback to total population."""
    # With working population
    assert calc_manpower_cap(100_000, 200_000) == 10_000
    assert calc_manpower_cap(55_555) == 5_555

    # Fallback to total population when pop_working is 0 or absent
    assert calc_manpower_cap(0, 80_000) == 8_000
    assert calc_manpower_cap(None, 50_000) == 5_000
    assert calc_manpower_cap(0, 0) == 0


def test_used_manpower_calculation():
    """Rule B4: Sum of all units owned weighted by crew."""
    units = {
        "soldiers": 1000,   # 1,000 * 1 = 1,000
        "tanks": 50,        # 50 * 4 = 200
        "destroyers": 10,   # 10 * 6 = 60
        "cruisers": 2,      # 2 * 5 = 10
        "submarines": 5,    # 5 * 6 = 30
        "spies": 100,       # 0
        "nukes": 5,         # 0
    }
    # Total: 1000 + 200 + 60 + 10 + 30 = 1300
    assert calc_used_manpower(units) == 1300

    # Also supports dict format with quantity field
    units_dict_format = {
        "soldiers": {"quantity": 500},
        "artillery": {"quantity": 10},  # 10 * 2 = 20
    }
    assert calc_used_manpower(units_dict_format) == 520


def test_free_manpower():
    assert calc_free_manpower(5000, 3100) == 1900
    assert calc_free_manpower(3000, 3100) == 0  # Over cap


def test_can_recruit_within_cap():
    cap = 5000
    used = 3100

    # Buying 500 soldiers requires 500 crew; 1900 free -> Allowed
    allowed, needed, free = can_recruit("soldiers", 500, used, cap)
    assert allowed is True
    assert needed == 500
    assert free == 1900

    # Buying 5 cruisers requires 25 crew; 1900 free -> Allowed
    allowed, needed, free = can_recruit("cruisers", 5, used, cap)
    assert allowed is True
    assert needed == 25
    assert free == 1900


def test_can_recruit_exceeding_cap():
    cap = 5000
    used = 3100

    # Buying 2100 soldiers requires 2100 crew; only 1900 free -> Denied
    allowed, needed, free = can_recruit("soldiers", 2100, used, cap)
    assert allowed is False
    assert needed == 2100
    assert free == 1900

    err_msg = format_manpower_error(needed, free)
    assert err_msg == "Not enough manpower: this needs 2100 crew, you have 1900 free (cap = 10% of working population)."


def test_can_recruit_when_already_over_cap():
    cap = 5000
    used = 5500  # Already over cap

    allowed, needed, free = can_recruit("soldiers", 1, used, cap)
    assert allowed is False
    assert needed == 1
    assert free == 0

    err_msg = format_manpower_error(needed, free)
    assert err_msg == "Not enough manpower: this needs 1 crew, you have 0 free (cap = 10% of working population)."
