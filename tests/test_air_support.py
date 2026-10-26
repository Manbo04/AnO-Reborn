"""Balance prototype phase 3: bombers attached to ground/naval attacks."""
import random

from attack_scripts import combat_helpers as ch
from wars.action_points import AP_COSTS

DEF = {"soldiers": 50000, "tanks": 2000, "artillery": 500}


def test_zero_bombers_is_noop():
    assert ch.compute_air_support(0, DEF, 500, 10000.0) == (0.0, 0.0, 0)


def test_units_default_has_no_support():
    from units import Units
    u = Units(1)
    assert u.support_bombers == 0
    rebuilt = Units.rebuild_from_dict(dict(u.__dict__))
    assert rebuilt.support_bombers == 0
    assert Units(1, support_bombers=7).support_bombers == 7


def test_fighter_cover_reduces_support_and_kills_bombers():
    rng = random.Random(1)
    s0, c0, l0 = ch.compute_air_support(100, DEF, 0, 1e9, rng=rng)
    s1, c1, l1 = ch.compute_air_support(100, DEF, 100, 1e9, rng=rng)
    assert c0 == 0 and l0 == 0 and s0 > 0
    assert c1 == 1.0 and s1 < s0 * 0.5 and l1 > 0
    assert l1 <= round(100 * ch.INTERCEPT_LOSS_MAX * 1.3)


def test_support_capped_by_attacker_score():
    s, _, _ = ch.compute_air_support(100000, DEF, 0, 1000.0)
    assert s <= ch.SUPPORT_CAP * 1000.0 + 1e-9


def test_air_support_ap_cost():
    assert AP_COSTS["air_support"] == ("air", ch.AIR_SUPPORT_AP_COST)
