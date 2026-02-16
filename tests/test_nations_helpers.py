from attack_scripts.nations_helpers import calculate_bonuses


class _FakeEnemy:
    def __init__(self, selected_units):
        self.selected_units = selected_units


def test_calculate_bonuses_basic():
    # 10 of target unit, total 110 -> unit_of_army ~= 9.90099
    # attack_effects[1] = 50 -> affected_bonus ~= 50 * 0.0990099 = 4.95049
    # return value ~= 4.95049 / 100 = 0.0495049
    enemy = _FakeEnemy({"soldiers": 10, "tanks": 100})
    v = calculate_bonuses((0, 50), enemy, "soldiers")
    assert 0.049 < v < 0.051


def test_calculate_bonuses_all_same_unit():
    enemy = _FakeEnemy({"fighters": 5})
    # unit_of_army = (5*100)/(5+1) = 83.3333%, attack_effects[1] = 20
    # affected_bonus = 20 * 0.833333 = 16.66666 -> return ~= 0.16666
    v = calculate_bonuses((None, 20), enemy, "fighters")
    assert 0.16 < v < 0.18
