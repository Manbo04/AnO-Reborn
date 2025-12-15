from units import Units


def test_attack_without_selected_units():
    u = Units(1)
    # No selected_units -> should return explanatory message
    assert u.attack("soldiers", "artillery") == "Units are not attached!"


def test_attack_with_unknown_interface():
    u = Units(1)
    u.selected_units = {"soldiers": 1}
    # Attacker unit name not found in interfaces -> None
    assert u.attack("nonexistent", "artillery") is None


def test_attack_soldier_vs_artillery():
    u = Units(1)
    u.selected_units = {"soldiers": 2}
    res = u.attack("soldiers", "artillery")
    assert isinstance(res, tuple)
    # Two soldiers with base damage 1 => 2; bonus should be 3 * amount = 6
    assert res == (2, 6)
