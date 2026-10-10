import pytest
pytestmark = pytest.mark.no_server

import sys
from unittest.mock import MagicMock
for _m in [
    "flask",
    "flask_limiter",
    "flask_limiter.util",
    "flask_socketio",
    "flask_login",
    "flask_wtf",
    "flask_wtf.csrf",
    "extensions",
    "psycopg2",
    "psycopg2.extras",
    "psycopg2.pool",
    "psycopg2.extensions",
    "celery",
    "redis",
    "dotenv",
]:
    if _m not in sys.modules:
        try:
            __import__(_m)
        except ImportError:
            sys.modules[_m] = MagicMock()

import datetime

import variables
from app_core.game_ticks import population as pop
from wars import aftermath

AFTER_FIX = variables.DISTRIBUTION_FIX_START + datetime.timedelta(hours=1)
BEFORE_FIX = variables.DISTRIBUTION_FIX_START - datetime.timedelta(hours=1)


def _provinces(uid, n, cities, land, population):
    return [
        {
            "userid": uid,
            "population": population // n,
            "citycount": cities // n,
            "land": land // n,
            "happiness": 50,
            "pollution": 50,
        }
        for _ in range(n)
    ]


def test_province_count_does_not_change_comfort():
    spread = pop.build_nation_contexts(_provinces(1, 80, 1760, 5840, 190_000_000))[1]
    packed = pop.build_nation_contexts(_provinces(1, 4, 1760, 5840, 190_000_000))[1]
    assert spread["comfort"] == packed["comfort"]


def test_comfort_keeps_early_slope_and_saturates():
    small = pop.nation_comfort(10, 10)
    assert 10_000_000 < small < 15_000_000  # ~750k/city + ~120k/land + 5M
    huge = pop.nation_comfort(100_000, 100_000)
    assert huge <= variables.NATION_COMFORT_BASE + variables.CITY_POP_CAP + variables.LAND_POP_CAP


def test_growth_scales_with_current_population():
    comfort = 800_000_000
    big = pop.calc_nation_growth(190_000_000, comfort, 1.0)
    smaller = pop.calc_nation_growth(150_000_000, comfort, 1.0)
    assert big > smaller > 0
    # Armed Farmers-like nation: was ~2.6M/h, now well under 1M/h.
    assert big < 1_000_000


def test_growth_frozen_removed_and_starved():
    # Freeze removed (vote 2026-10-09): there is no frozen flag any more
    import inspect
    assert "frozen" not in inspect.signature(pop.calc_nation_growth).parameters
    assert pop.calc_nation_growth(1_000_000, 50_000_000, 1.0) > 0
    # Starvation still zeroes growth
    assert pop.calc_nation_growth(1_000_000, 50_000_000, 0.0) == 0


def test_no_hard_cap_past_comfort_but_slow():
    comfort = 100_000_000
    g = pop.calc_nation_growth(400_000_000, comfort, 1.0)
    assert 0 < g < 400_000_000 * variables.POP_GROWTH_RATE * 0.1


def test_distribution_bug_fixed_after_start():
    # 1 food bank (250k people) cannot feed 191M people.
    need = 191_000_000 // variables.RATIONS_PER
    comfort = 800_000_000
    before = pop.distributable_rations(304_017, 250_000, 191_000_000, comfort, now=BEFORE_FIX)
    after = pop.distributable_rations(304_017, 250_000, 191_000_000, comfort, now=AFTER_FIX)
    assert before >= need  # old bug: counted as fully fed
    assert after == 250_000 // variables.RATIONS_PER
    assert after / need < 0.01


def test_overcrowding_shrinks_distribution():
    assert pop.overcrowding_efficiency(100, 100) == 1.0
    assert abs(pop.overcrowding_efficiency(400, 100) - 0.5) < 1e-9
    full = pop.distributable_rations(10**12, 4_000_000_000, 1_000_000_000, 1_000_000_000, now=AFTER_FIX)
    crowded = pop.distributable_rations(10**12, 4_000_000_000, 4_000_000_000, 1_000_000_000, now=AFTER_FIX)
    assert crowded * 2 == full


def test_province_delta_starvation():
    assert pop.calc_province_population_delta(1_000_000, 10_000, 0.5, 1.0, False) == 5_000
    assert pop.calc_province_population_delta(1_000_000, 0, 1.0, 0.0, False) == -10_000
    assert pop.calc_province_population_delta(1_000_000, 0, 1.0, 0.0, True) == 0


def test_civilian_death_pct():
    assert aftermath.civilian_death_pct("ground", {}, "annihilation") == 0.03
    assert aftermath.civilian_death_pct(None, {}, "close victory") == 0.01
    assert aftermath.civilian_death_pct("air", {"bombers": 5}, "definite victory") == 0.04
    assert aftermath.civilian_death_pct("air", {"fighters": 5}, "annihilation") == 0.0
    assert aftermath.civilian_death_pct("naval", {}, "annihilation") == 0.0


def test_bomber_ground_losses_capped_per_bomber():
    army = {"soldiers": 100_000, "tanks": 5_000}
    assert aftermath.bomber_ground_losses(1, army, "annihilation") == {"soldiers": 25, "tanks": 2}
    big = aftermath.bomber_ground_losses(100_000, army, "annihilation")
    assert big == {"soldiers": 15_000, "tanks": 750}
    assert aftermath.bomber_ground_losses(0, army, "annihilation") == {}


def test_province_price_steeper_after_20():
    from province import province_price_for_count

    assert province_price_for_count(0) == 2_000_000
    assert province_price_for_count(1) == 5_000_000
    assert province_price_for_count(20) == int(8_000_000 * (1 + 0.16 * 20))
    assert province_price_for_count(40) > 250_000_000
    assert province_price_for_count(79) > 10_000_000_000


def test_catchup_boost_helps_small_nations_not_whales():
    comfort = 153_000_000
    rate = pop.variables.POP_GROWTH_RATE
    seed = pop.variables.POP_GROWTH_SEED_RATE
    small = pop.calc_nation_growth(11_000_000, comfort, 1.0)
    # ~2.4x on the rate term: 11M people at 7% of comfort
    assert small > 2.2 * rate * 11_000_000
    # big city-heavy nation far below comfort: no boost past CATCHUP_POP
    af_comfort = 790_000_000
    af = pop.calc_nation_growth(190_000_000, af_comfort, 1.0)
    dim = 1 - (190_000_000 / af_comfort) ** 2
    assert af == int(round(dim * (rate * 190_000_000 + seed * af_comfort)))
    # over comfort: no boost, same as before
    over = pop.calc_nation_growth(400_000_000, comfort, 1.0)
    floor = pop.variables.POP_GROWTH_DIMINISHING_FLOOR
    assert over == int(round(floor * (rate * 400_000_000 + seed * comfort)))
