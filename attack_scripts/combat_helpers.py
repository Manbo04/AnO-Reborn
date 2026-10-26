"""Combat-related helpers extracted from the legacy `Nations.py`.

These functions are intentionally small and unit-testable so the large
`Nations.py` can be refactored incrementally.
"""

from typing import Dict, Tuple

from attack_scripts.nations_helpers import calculate_bonuses


def compute_user_army_strength(user_id: int) -> float:
    """Compute total army strength from normalized military tables.

    Strength uses the average of `base_attack` and `base_defense` per unit,
    multiplied by the owned quantity.
    """
    from database import get_db_cursor
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


# --- Balance prototype (2026-10) -------------------------------------------
# Presence is value-weighted: each unit contributes UNIT_POWER[unit] / 150, so
# equal gold buys roughly equal presence (UNIT_POWER ~= price / 250). Before
# this, every unit counted 1/150 regardless of type, so soldiers dominated.
PRESENCE_DIVISOR = 150.0
UNIT_POWER = {
    "soldiers": 1,
    "tanks": 28,
    "artillery": 56,
    "bombers": 88,
    "fighters": 115,
    "apaches": 112,
    "destroyers": 104,
    "cruisers": 192,
    "submarines": 160,
    "aircraft_carriers": 880,
}

# Battle roll: each side's score is multiplied by uniform(ROLL_LOW, ROLL_HIGH).
# Replaces the old flat +uniform(1, 5), which was negligible next to army size
# so the bigger army won every time.
ROLL_LOW = 0.6
ROLL_HIGH = 1.4


def battle_roll(score: float, rng: object = None) -> float:
    import random as _random

    return float(score) * (rng or _random).uniform(ROLL_LOW, ROLL_HIGH)


# Artillery shells dug-in positions: an all-artillery attack ignores this share
# of the defender's entrenchment bonus (scaled by artillery's share of the
# attacker's presence).
ARTILLERY_ENTRENCH_PIERCE = 0.6


def artillery_entrenchment_pierce(selected_units_list: list, selected_units: Dict[str, int]) -> float:
    total = compute_unit_amount_bonus(selected_units_list, selected_units)
    if total <= 0 or "artillery" not in (selected_units_list or []):
        return 0.0
    arty = compute_unit_amount_bonus(["artillery"], selected_units)
    return ARTILLERY_ENTRENCH_PIERCE * arty / total


def compute_unit_amount_bonus(
    selected_units_list: list, selected_units: Dict[str, int]
) -> float:
    """Value-weighted presence: sum(unit_count * UNIT_POWER[unit] / 150)."""
    total = 0.0
    for unit in selected_units_list:
        count = selected_units.get(unit, 0) or 0
        total += count * UNIT_POWER.get(unit, 1) / PRESENCE_DIVISOR
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


def apply_combat_modifiers(
    attacker_unit_amount_bonuses: float,
    attacker_bonus: float,
    defender_unit_amount_bonuses: float,
    defender_bonus: float,
    entrenchment_level: int = 0,
    attacker_intel: int = 0,
    is_ground: bool = True,
    entrenchment_pierce: float = 0.0,
) -> Tuple[float, float, float, float]:
    """Apply entrenchment (+5% per level to ground defense) and intel (+intel/10 % to attack strength).

    entrenchment_pierce (0..1) is the share of the entrenchment bonus the
    attacker ignores (see artillery_entrenchment_pierce)."""
    from wars.action_points import entrenchment_defense_multiplier, intel_attack_multiplier

    if is_ground and entrenchment_level:
        e_mult = entrenchment_defense_multiplier(entrenchment_level)
        pierce = max(0.0, min(1.0, float(entrenchment_pierce or 0)))
        e_mult = 1.0 + (e_mult - 1.0) * (1.0 - pierce)
        defender_unit_amount_bonuses *= e_mult
        defender_bonus *= e_mult

    if attacker_intel:
        i_mult = intel_attack_multiplier(attacker_intel)
        attacker_unit_amount_bonuses *= i_mult
        attacker_bonus *= i_mult

    return (
        attacker_unit_amount_bonuses,
        attacker_bonus,
        defender_unit_amount_bonuses,
        defender_bonus,
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
    """Compute morale loss for a defeated side based on its force and its victor.

    Both attackers and defenders lose morale when they lose. The stronger the
    winning side relative to the combined forces, the larger the morale hit.
    """
    attacker_strength = compute_strength(attacker_units)
    defender_strength = compute_strength(defender_units)
    winner_strength = defender_strength if winner_is_defender else attacker_strength
    advantage_factor = winner_strength / (attacker_strength + defender_strength + 1e-9)

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
    floor = morale_floor(win_type, loser_units)
    computed_morale_delta = max(floor, computed_morale_delta)
    computed_morale_delta = min(MORALE_DELTA_CAP, computed_morale_delta)
    return computed_morale_delta


# Morale floor per won battle, by how decisive the win was (win_type is the
# winner/loser score ratio). Wars between equals should end in ~5-15 wins.
MORALE_FLOOR_CLOSE = 6  # win_type < 1.25
MORALE_FLOOR_CLEAR = 12  # 1.25 <= win_type < 1.75
MORALE_FLOOR_CRUSHING = 20  # win_type >= 1.75
MORALE_FLOOR_EMPTY = 20  # loser fielded nothing
MORALE_DELTA_CAP = 25


def morale_floor(win_type: float, loser_units: dict = None) -> int:
    if not any((v or 0) > 0 for v in (loser_units or {}).values()):
        return MORALE_FLOOR_EMPTY
    wt = float(win_type or 0)
    if wt >= 1.75:
        return MORALE_FLOOR_CRUSHING
    if wt >= 1.25:
        return MORALE_FLOOR_CLEAR
    return MORALE_FLOOR_CLOSE


def zero_out_empty_side(
    attacker_chance: float,
    defender_chance: float,
    attacker_unit_amount_bonuses: float,
    defender_unit_amount_bonuses: float,
) -> tuple:
    """A side with no effective force gets zero chance.

    The attacker check comes FIRST: an attacker with nothing usable (e.g. only
    units whose upkeep ran out, which contribute no presence bonus) must not
    win just because the defender also has nothing in that domain. Previously
    the empty-defender rule ran first, so such an attack counted as a free win
    (loot, razing, morale damage). With both sides empty the defender holds.

    Returns (attacker_chance, defender_chance)."""
    if attacker_unit_amount_bonuses == 0:
        return 0, defender_chance
    if defender_unit_amount_bonuses == 0:
        return attacker_chance, 0
    return attacker_chance, defender_chance


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


# Casualty tuning (share of the committed force of each unit type)
WINNER_LOSS_PER_POINT = 0.04
WINNER_MAX_LOSS_FRAC = 0.30
LOSER_LOSS_PER_POINT = 0.04
LOSER_MAX_LOSS_FRAC = 0.35


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

    for w_unit in winner_units_list:
        w_sent = winner_units.get(w_unit, 0) or 0
        if w_sent > 0:
            w_frac = min(WINNER_MAX_LOSS_FRAC, WINNER_LOSS_PER_POINT * winner_casulties)
            w_cas = min(w_sent, max(1, round(w_sent * w_frac * _rng.uniform(0.7, 1.3))))
            winner_pairs.append((w_unit, w_cas))

    for l_unit in loser_units_list:
        l_sent = loser_units.get(l_unit, 0) or 0
        if l_sent > 0:
            l_frac = min(LOSER_MAX_LOSS_FRAC, LOSER_LOSS_PER_POINT * win_type)
            l_cas = min(l_sent, max(1, round(l_sent * l_frac * _rng.uniform(0.8, 1.2))))
            loser_pairs.append((l_unit, l_cas))

    return winner_pairs, loser_pairs


# --- Air support for ground/naval attacks (balance prototype) ---------------
# The attacker may attach bombers to a ground or naval attack. They don't
# fight as a stack; they add a support score to the attacking side:
#   (bomber presence + bomber counter bonuses vs the defending units)
#   x SUPPORT_FACTOR x (1 - COVER_EFFECT x cover),
# capped at SUPPORT_CAP x the attacker's own (pre-roll) score, where cover is
# min(1, defender fighter presence / bomber presence). The defender's fighters
# also shoot attached bombers down (up to INTERCEPT_LOSS_MAX of them at full
# cover). No attached bombers -> zero support, i.e. old behaviour.
SUPPORT_FACTOR = 1.3
COVER_EFFECT = 0.75
SUPPORT_CAP = 0.6
INTERCEPT_LOSS_MAX = 0.15
AIR_SUPPORT_AP_COST = 2  # air AP, on top of the ground/naval attack's cost


def compute_air_support(
    bombers: int,
    defender_units: Dict[str, int],
    defender_fighters: int,
    attacker_score: float,
    rng: object = None,
) -> Tuple[float, float, int]:
    """Return (support_score, cover, bombers_lost)."""
    import random as _random

    _rng = rng or _random
    bombers = max(0, int(bombers or 0))
    if bombers <= 0:
        return 0.0, 0.0, 0
    from units import BomberUnit

    bomber_presence = compute_unit_amount_bonus(["bombers"], {"bombers": bombers})
    total = sum((v or 0) for v in (defender_units or {}).values())
    counter = 0.0
    for unit, count in (defender_units or {}).items():
        if not count:
            continue
        bonus = BomberUnit(bombers).attack(unit)[1]
        counter += bonus * (count / (total + 1)) / 100.0
    fighter_presence = compute_unit_amount_bonus(
        ["fighters"], {"fighters": max(0, int(defender_fighters or 0))}
    )
    cover = min(1.0, fighter_presence / bomber_presence)
    score = (bomber_presence + counter) * SUPPORT_FACTOR * (1.0 - COVER_EFFECT * cover)
    score = min(score, SUPPORT_CAP * max(0.0, float(attacker_score or 0)))
    lost = 0
    if cover > 0:
        lost = min(bombers, int(round(bombers * INTERCEPT_LOSS_MAX * cover * _rng.uniform(0.7, 1.3))))
    return score, cover, lost
