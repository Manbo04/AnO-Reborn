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
