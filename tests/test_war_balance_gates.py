"""Gates from player reports: tiny forces, opening MAP, strike disruption.

Pure combat math. The even-war MAP-refill measurement lives in
scripts/simulate_war_balance.py (needs the same constants).
"""

import random

import pytest

from attack_scripts import combat_helpers as ch
from units import Units

pytestmark = pytest.mark.no_server

DOMAINS = {
    "ground": "soldiers",
    "air": "fighters",
    "naval": "destroyers",
}


def _side(units, uid):
    u = Units(uid, selected_units=dict(units), selected_units_list=list(units))
    u._unusable_units_cache = set()
    return u


def _attacker_wins(att, den, rng, suppress=None, support=0, fighters=0):
    a = _side(att, 1)
    d = _side(den, 2)
    aa, da, ab, db, _ = ch.compute_engagement_metrics(a, d)
    if suppress:
        pen = ch.suppression_penalty(den, suppress)
        da *= 1.0 - pen
        db *= 1.0 - pen
    if support:
        sup, *_rest = ch.compute_air_support(support, den, fighters, aa + ab, rng=rng)
        ab += sup
    aa, ab, da, db = ch.apply_combat_modifiers(
        aa,
        ab,
        da,
        db,
        entrenchment_level=0,
        attacker_intel=0,
        is_ground=False,
        entrenchment_pierce=0.0,
    )
    ac = ch.battle_roll(aa + ab, rng)
    dc = ch.battle_roll(da + db, rng)
    ac, dc = ch.zero_out_empty_side(ac, dc, aa, da)
    return ac > dc


def _rate(att, den, n, seed, **kw):
    rng = random.Random(seed)
    wins = sum(1 for _ in range(n) if _attacker_wins(att, den, rng, **kw))
    return wins / n


@pytest.mark.parametrize("domain", list(DOMAINS))
@pytest.mark.parametrize(
    "mode",
    ["plain", "support", "suppressed", "both"],
)
def test_one_never_beats_a_hundred(domain, mode):
    unit = DOMAINS[domain]
    kw = {}
    if mode in ("support", "both"):
        kw["support"] = 100000
        kw["fighters"] = 0
    if mode in ("suppressed", "both"):
        kw["suppress"] = {unit: ch.SUPPRESS_MAX}
    rate = _rate({unit: 1}, {unit: 100}, 80, seed=1, **kw)
    assert rate == 0.0


def test_one_never_beats_sixty_billion():
    for domain, unit in DOMAINS.items():
        for support in (0, 50000):
            rate = _rate(
                {unit: 1},
                {unit: 60_000_000_000},
                20,
                seed=2,
                support=support,
                suppress={unit: ch.SUPPRESS_MAX},
            )
            assert rate == 0.0, domain


def test_half_strength_never_wins():
    base = {"soldiers": 80000, "tanks": 2000, "artillery": 800}
    att = {u: max(1, c // 2) for u, c in base.items()}
    assert _rate(att, base, 200, seed=3) == 0.0


def test_win_rate_curve():
    base = {"soldiers": 80000, "tanks": 2000, "artillery": 800}
    bands = {1.1: (0.55, 0.85), 1.25: (0.78, 0.97), 2.0: (0.97, 1.01)}
    for ratio, (lo, hi) in bands.items():
        att = {u: max(1, int(c * ratio)) for u, c in base.items()}
        rate = _rate(att, base, 400, seed=4)
        assert lo <= rate <= hi, (ratio, rate)


def test_disruption_does_not_let_tanks_be_ignored():
    # Full disruption is a 1.25x fight (1 / 0.8), not an automatic win.
    rate = _rate(
        {"tanks": 1000},
        {"tanks": 1000},
        400,
        seed=5,
        suppress={"tanks": ch.SUPPRESS_MAX},
    )
    assert 0.75 < rate < 0.97


def test_opening_maps_cannot_zero_morale():
    from app_core.bots.profiles import army_for_strength

    for strength in (200_000, 1_000_000):
        army = army_for_strength("Balanced", strength)
        # One side loses every opening attack at the widest roll, no casualties.
        # 6 attacks is one nation's whole starting pool (2 per branch).
        delta = ch.compute_morale_delta(
            army, army, army, False, ch.ROLL_HIGH / ch.ROLL_LOW
        )
        assert 6 * delta < ch.MORALE_START, (strength, delta)
        assert 6 * ch.MORALE_DELTA_CAP < ch.MORALE_START


def test_even_war_survives_the_opening_maps():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "scripts" / "simulate_war_balance.py"
    spec = importlib.util.spec_from_file_location("simulate_war_balance", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rng = random.Random(11)
    army = mod.army_for_strength("Balanced", 200_000)
    for _ in range(4):
        _battles, hours, _winner = mod.simulate_war("new", army, rng)
        assert hours >= 1
