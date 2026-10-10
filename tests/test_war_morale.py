import pytest

pytestmark = pytest.mark.no_server

from attack_scripts.combat_helpers import compute_morale_delta, compute_strength


def test_attacker_loss_costs_zero_morale():
    """Rule B3: When the attacker loses a battle (winner_is_defender=True),

    the attacker's morale must not drop (delta is 0).
    """
    attacker_units = {"soldiers": 1000, "tanks": 50}
    defender_units = {"soldiers": 2000, "tanks": 100}
    loser_units = attacker_units

    # Attacker lost (winner is defender) for various win types
    for win_type in [1.0, 2.0, 3.0, 4.0]:
        delta = compute_morale_delta(
            loser_units=loser_units,
            attacker_units=attacker_units,
            defender_units=defender_units,
            winner_is_defender=True,
            win_type=win_type,
        )
        assert delta == 0


def test_defender_loss_costs_morale():
    """Rule B3: When the attacker wins (winner_is_defender=False),

    the defender still loses morale as usual.
    """
    attacker_units = {"soldiers": 2000, "tanks": 100}
    defender_units = {"soldiers": 1000, "tanks": 50}
    loser_units = defender_units

    for win_type in [1.0, 2.0, 3.0, 4.0]:
        delta = compute_morale_delta(
            loser_units=loser_units,
            attacker_units=attacker_units,
            defender_units=defender_units,
            winner_is_defender=False,
            win_type=win_type,
        )
        assert delta > 0
        assert 1 <= delta <= 200


def test_combat_strength_pure():
    """Ensure compute_strength calculates weighted army power."""
    units = {"soldiers": 1000, "tanks": 10, "icbms": 2}
    # soldiers: 1000 * 0.0002 = 0.2
    # tanks: 10 * 0.02 = 0.2
    # icbms: 2 * 5 = 10
    expected = 0.2 + 0.2 + 10.0
    strength = compute_strength(units)
    assert abs(strength - expected) < 1e-5
