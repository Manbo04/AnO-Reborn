"""Combat-related helpers extracted from the legacy `Nations.py`.

These functions are intentionally small and unit-testable so the large
`Nations.py` can be refactored incrementally.
"""

import math
from typing import Dict, Tuple

from attack_scripts.nations_helpers import calculate_bonuses
from database import get_db_cursor


def compute_user_army_strength(user_id: int) -> float:
    """Compute total army strength from normalized military tables.

    Strength uses the average of `base_attack` and `base_defense` per unit,
    multiplied by the owned quantity.
    """
    with get_db_cursor() as db:
        db.execute(
            """
            SELECT
                COALESCE(
                    SUM(um.quantity * ((ud.base_attack + ud.base_defense) / 2.0)),
                    0
                )
            FROM user_military um
            JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
            WHERE um.user_id=%s AND ud.is_active=TRUE
            """,
            (user_id,),
        )
        row = db.fetchone()
        return float(row[0] or 0)


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

    Unusable units (maintenance resource depleted) are excluded from the raw
    presence bonus AND return (0, 0) from attack(), so they contribute exactly
    zero combat power on both offense and defense.
    """
    # Fetch unusable unit sets once per fight (lazy-cached on the Units objects)
    attacker_unusable = attacker.unusable_units
    defender_unusable = defender.unusable_units

    # Unit-amount bonuses exclude unusable units so their sheer numbers don't
    # grant a tactical presence advantage while they are immobilised.
    attacker_unit_amount_bonuses = compute_unit_amount_bonus(
        [u for u in attacker.selected_units_list if u not in attacker_unusable],
        attacker.selected_units,
    )
    defender_unit_amount_bonuses = compute_unit_amount_bonus(
        [u for u in defender.selected_units_list if u not in defender_unusable],
        defender.selected_units,
    )

    attacker_bonus = 0.0
    defender_bonus = 0.0
    dealt_infra_damage = 0.0

    # attacker -> defender contributions
    for attacker_unit in attacker.selected_units_list:
        for unit in defender.selected_units_list:
            attack_effects = attacker.attack(attacker_unit, unit)
            if not isinstance(attack_effects, tuple):
                continue
            attacker_bonus += calculate_bonuses(attack_effects, defender, unit)
            dealt_infra_damage += attack_effects[0]

    # defender -> attacker contributions
    for defender_unit in defender.selected_units_list:
        for unit in attacker.selected_units_list:
            defender_attack_effects = defender.attack(defender_unit, unit)
            if not isinstance(defender_attack_effects, tuple):
                continue
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


# Morale per battle (2026-10-04). It used to scale with the loser's raw unit
# count (clamped 1..200 against a 100 pool), so once supply stopped capping
# army size a single big battle would end a war. Now it depends on how
# decisive the win was and how serious the winning force was, never on raw
# army size: a decent-sized win costs the loser ~10-20 morale, an
# annihilation ~40, a token 1-unit raid 1.
MORALE_PER_WIN = 12
MORALE_MAX_PER_BATTLE = 40
# Supply value of a winning force that counts as a full-strength battle.
MORALE_FULL_COMMIT_SUPPLY = 2000


def _supply_value(units: dict) -> float:
    try:
        from wars.supply import unit_supply_costs

        costs = unit_supply_costs()
    except Exception:
        costs = {"soldiers": 1}
    return float(
        sum(max(0, count or 0) * costs.get(name, 5) for name, count in (units or {}).items())
    )


def compute_morale_delta(
    loser_units: dict,
    attacker_units: dict,
    defender_units: dict,
    winner_is_defender: bool,
    win_type: float,
) -> int:
    """Morale the loser drops after one battle (1..MORALE_MAX_PER_BATTLE).

    `loser_units` is kept for call compatibility; losses no longer depend on
    the loser's size.
    """
    winner_units = defender_units if winner_is_defender else attacker_units
    commitment = min(1.0, math.sqrt(_supply_value(winner_units) / MORALE_FULL_COMMIT_SUPPLY))
    decisiveness = min(max(float(win_type or 1.0), 1.0), 5.0) ** 0.75
    delta = int(round(MORALE_PER_WIN * decisiveness * commitment))
    return max(1, min(MORALE_MAX_PER_BATTLE, delta))


def resolve_battle_outcome(
    attacker_chance: float,
    defender_chance: float,
    attacker_unit_amount_bonuses: float,
    defender_unit_amount_bonuses: float,
) -> tuple:
    """Determine winner/loser, win_type and winner_casulties using original logic.

    Returns: (winner_is_defender: bool, win_type: float, winner_casulties: float)
    """
    if defender_chance >= attacker_chance:
        # defender wins
        if attacker_unit_amount_bonuses == 0:
            return True, 5, 0
        return (
            True,
            (defender_chance / attacker_chance),
            ((1 + attacker_chance) / defender_chance),
        )
    else:
        # attacker wins
        if defender_unit_amount_bonuses == 0:
            return False, 5, 0
        return (
            False,
            (attacker_chance / defender_chance),
            ((1 + defender_chance) / attacker_chance),
        )


LOSER_LOSS_PCT_PER_WIN_TYPE = 0.03
LOSER_LOSS_MAX_PCT = 0.18
WINNER_LOSS_PCT = 0.03


def compute_unit_casualties(
    winner_casulties: float,
    win_type: float,
    winner_units_list: list,
    loser_units_list: list,
    winner_units: dict = None,
    loser_units: dict = None,
    rng: object = None,
) -> tuple:
    """Compute casualty values for each unit pair in the engagement.

    `winner_units`/`loser_units` map unit_type -> amount actually committed to this
    fight (i.e. `Units.selected_units`). A unit type present in the composition list
    but sent with amount 0 takes no casualties, and casualties for a sent unit type
    are capped at the amount sent — a side can never lose more of a unit type than it
    actually committed to this specific engagement, regardless of total stockpile.

    Returns two lists of (unit_name, casualties) for winner and loser respectively.
    The function is pure if a deterministic RNG is provided (useful for tests).
    """
    import random as _random

    _rng = rng or _random
    winner_units = winner_units or {}
    loser_units = loser_units or {}
    winner_pairs = []
    loser_pairs = []

    # Share-of-force losses (2026-10-04) on top of the old flat numbers, so
    # big battles cost big armies: the loser loses ~3% (close fight) up to
    # LOSER_LOSS_MAX_PCT (rout) of what it sent, the winner less. Small
    # battles keep the old flat losses because max() picks the larger.
    decisive = min(max(float(win_type or 1.0), 1.0), 5.0)
    loser_pct = min(LOSER_LOSS_MAX_PCT, LOSER_LOSS_PCT_PER_WIN_TYPE * decisive)
    winner_pct = min(
        loser_pct, WINNER_LOSS_PCT * min(max(float(winner_casulties or 0), 0.0), 1.0)
    )

    for w_unit, l_unit in zip(winner_units_list, loser_units_list):
        w_sent = winner_units.get(w_unit, 0) or 0
        l_sent = loser_units.get(l_unit, 0) or 0

        if w_sent > 0:
            w_flat = winner_casulties * _rng.uniform(2, 10) * 2
            w_share = w_sent * winner_pct * _rng.uniform(0.8, 1.2)
            w_cas = min(w_sent, max(w_flat, w_share))
            winner_pairs.append((w_unit, w_cas))

        if l_sent > 0:
            l_flat = win_type * _rng.uniform(2, 10.5) * 2
            l_share = l_sent * loser_pct * _rng.uniform(0.8, 1.2)
            l_cas = min(l_sent, max(l_flat, l_share))
            loser_pairs.append((l_unit, l_cas))

    return winner_pairs, loser_pairs
