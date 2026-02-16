import pytest

from attack_scripts.combat_helpers import (
    compute_unit_amount_bonus,
    compute_engagement_metrics,
    compute_morale_delta,
    compute_strength,
    resolve_battle_outcome,
    compute_unit_casualties,
)


class _FakeUnit:
    def __init__(self, selected_units_list, selected_units, damage, effect):
        self.selected_units_list = selected_units_list
        self.selected_units = selected_units
        self._damage = damage
        self._effect = effect

    def attack(self, unit_from, unit_to):
        # deterministic simple attack signature for tests
        return (self._damage, self._effect)


def test_compute_unit_amount_bonus():
    lst = ["a", "b"]
    counts = {"a": 150, "b": 0}
    assert compute_unit_amount_bonus(lst, counts) == 1.0


def test_compute_engagement_metrics_simple():
    attacker = _FakeUnit(["u1"], {"u1": 150}, damage=2, effect=10)
    defender = _FakeUnit(["u2"], {"u2": 150}, damage=3, effect=5)

    (
        att_amt_bonus,
        def_amt_bonus,
        att_bonus,
        def_bonus,
        dealt_infra_damage,
    ) = compute_engagement_metrics(attacker, defender)

    assert att_amt_bonus == 1.0
    assert def_amt_bonus == 1.0
    assert 0.099 < att_bonus < 0.100
    assert 0.049 < def_bonus < 0.050
    assert dealt_infra_damage == 2.0


def test_compute_morale_delta_and_strength():
    attacker_units = {"soldiers": 100, "tanks": 5}
    defender_units = {"soldiers": 80, "tanks": 2}
    loser_units = defender_units

    # If attacker wins (winner_is_defender=False) the computed delta should be > 0
    delta = compute_morale_delta(
        loser_units, attacker_units, defender_units, False, win_type=2
    )
    assert isinstance(delta, int)
    assert delta >= 1 and delta <= 200

    # Strength sanity checks
    a_strength = compute_strength(attacker_units)
    d_strength = compute_strength(defender_units)
    assert a_strength > 0
    assert d_strength > 0
    assert a_strength != d_strength


def test_resolve_battle_outcome_and_casualties_deterministic():
    # defender wins with attacker_unit_amount_bonuses == 0 -> special case
    winner_is_def, win_type, winner_cas = resolve_battle_outcome(1.0, 2.0, 0.0, 0.1)
    assert winner_is_def is True
    assert win_type == 5
    assert winner_cas == 0

    # regular outcome where attacker wins
    winner_is_def, win_type, winner_cas = resolve_battle_outcome(3.0, 1.0, 0.5, 0.5)
    assert winner_is_def is False
    assert win_type == pytest.approx(3.0 / 1.0)
    assert winner_cas == pytest.approx((1 + 1.0) / 3.0)

    # casualty computation deterministic with seeded RNG
    import random

    rng = random.Random(0)
    winner_pairs, loser_pairs = compute_unit_casualties(
        winner_cas, win_type, ["u1", "u2"], ["v1", "v2"], rng=rng
    )
    assert len(winner_pairs) == 2
    assert len(loser_pairs) == 2
    # casualty values should be positive floats
    assert all(a > 0 for _, a in winner_pairs)
    assert all(a > 0 for _, a in loser_pairs)
