from attack_scripts.combat_helpers import (
    compute_unit_amount_bonus,
    compute_engagement_metrics,
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
