"""Combat-related helpers extracted from the legacy `Nations.py`.

These functions are intentionally small and unit-testable so the large
`Nations.py` can be refactored incrementally.
"""
from typing import Dict, Tuple

from attack_scripts.nations_helpers import calculate_bonuses


def compute_unit_amount_bonus(
    selected_units_list: list, selected_units: Dict[str, int]
) -> float:
    """Compute the unit-amount-derived bonus used in combat loops.

    Mirrors the original logic in `Nations.fight`: sum(unit_count/150)
    """
    total = 0.0
    for unit in selected_units_list:
        total += (selected_units.get(unit, 0) or 0) / 150.0
    return total


def compute_engagement_metrics(
    attacker: object, defender: object
) -> Tuple[float, float, float, float, float]:
    """Run the inner fight loops and return computed metrics.

    Returns a tuple:
      (attacker_unit_amount_bonuses,
       defender_unit_amount_bonuses,
       attacker_bonus,
       defender_bonus,
       dealt_infra_damage)

    The helper calls `attack(..)` on the provided attacker/defender objects and
    delegates per-unit bonus math to `calculate_bonuses`.
    """
    attacker_unit_amount_bonuses = compute_unit_amount_bonus(
        attacker.selected_units_list, attacker.selected_units
    )
    defender_unit_amount_bonuses = compute_unit_amount_bonus(
        defender.selected_units_list, defender.selected_units
    )

    attacker_bonus = 0.0
    defender_bonus = 0.0
    dealt_infra_damage = 0.0

    # attacker -> defender contributions
    for attacker_unit in attacker.selected_units_list:
        for unit in defender.selected_units_list:
            attack_effects = attacker.attack(attacker_unit, unit)
            attacker_bonus += calculate_bonuses(attack_effects, defender, unit)
            dealt_infra_damage += attack_effects[0]

    # defender -> attacker contributions
    for defender_unit in defender.selected_units_list:
        for unit in attacker.selected_units_list:
            defender_attack_effects = defender.attack(defender_unit, unit)
            defender_bonus += calculate_bonuses(defender_attack_effects, attacker, unit)

    return (
        attacker_unit_amount_bonuses,
        defender_unit_amount_bonuses,
        attacker_bonus,
        defender_bonus,
        dealt_infra_damage,
    )


# Morale/strength helpers extracted from Nations.fight to keep the combat
# computations pure and testable.
def compute_strength(units: dict) -> float:
    """Compute a numeric strength for a side using unit morale weights.

    The weights mirror the original `Nations` implementation and are kept
    local to the helper to avoid mutating global state during refactor.
    """
    unit_morale_weights = {
        "soldiers": 0.0002,
        "artillery": 0.01,
        "tanks": 0.02,
        "bombers": 0.03,
        "fighters": 0.03,
        "apaches": 0.025,
        "destroyers": 0.03,
        "cruisers": 0.04,
        "submarines": 0.04,
        "spies": 0.0,
        "icbms": 5,
        "nukes": 12,
    }

    total = 0.0
    for unit_name, count in (units or {}).items():
        total += (count or 0) * unit_morale_weights.get(unit_name, 0.01)
    return total


def compute_morale_delta(
    loser_units: dict,
    attacker_units: dict,
    defender_units: dict,
    winner_is_defender: bool,
    win_type: float,
) -> int:
    """Compute the morale delta for the loser based on unit composition.

    Returns an integer delta (clamped 1..200) — matches the behaviour in
    `Nations.fight` but is now testable in isolation.
    """
    attacker_strength = compute_strength(attacker_units)
    defender_strength = compute_strength(defender_units)

    advantage = attacker_strength / (attacker_strength + defender_strength + 1e-9)
    advantage_factor = 1.0 - advantage if winner_is_defender else advantage

    base_loser_value = 0.0
    for unit_name, count in (loser_units or {}).items():
        # re-use the small default weight for unknown units
        weight = {
            "soldiers": 0.0002,
            "artillery": 0.01,
            "tanks": 0.02,
            "bombers": 0.03,
            "fighters": 0.03,
            "apaches": 0.025,
            "destroyers": 0.03,
            "cruisers": 0.04,
            "submarines": 0.04,
            "spies": 0.0,
            "icbms": 5,
            "nukes": 12,
        }.get(unit_name, 0.01)
        base_loser_value += (count or 0) * weight

    computed_morale_delta = int(
        round(base_loser_value * advantage_factor * win_type * 0.1)
    )
    computed_morale_delta = max(1, computed_morale_delta)
    computed_morale_delta = min(200, computed_morale_delta)
    return computed_morale_delta
