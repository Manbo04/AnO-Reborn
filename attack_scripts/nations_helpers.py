"""Small helpers extracted from the large `Nations.py` module.

Goal: start a progressive refactor by moving small, well-contained functions
out of the big legacy file so they can be tested and maintained separately.
"""
from __future__ import annotations

from typing import Any


def calculate_bonuses(attack_effects: Any, enemy_object: Any, target: str) -> float:
    """Compute the fractional bonus contribution from an attack effect.

    This was previously defined inside `attack_scripts/Nations.py` and is a
    pure helper that depends only on `attack_effects` and a small
    `enemy_object` shape (must expose `selected_units: Mapping[str, int]`).

    Returns a small float (e.g. 0.05) suitable for additive bonus math.
    """
    defending_unit_amount = enemy_object.selected_units[target]
    enemy_units_total_amount = sum(enemy_object.selected_units.values())

    # percentage of the enemy's relevant unit type in the force
    unit_of_army = (defending_unit_amount * 100) / (enemy_units_total_amount + 1)

    # scale by the attack_effects magnitude and normalize
    affected_bonus = attack_effects[1] * (unit_of_army / 100)

    # return normalized small value (keeps parity with previous behaviour)
    return affected_bonus / 100
