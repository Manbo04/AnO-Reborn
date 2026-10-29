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
# Live master added a flat uniform(1, 5) on top of presence (count/150). That
# roll is 4 points wide, so any count gap under about 600 units sits inside it:
# 1 fighter beats 100 about a third of the time. A literal 60-billion stack is
# presence ~4e8 and the flat roll cannot beat it; players describing "25% vs
# sixty billion" are describing that same size-blind roll. Multiplying by
# 0.8-1.2 makes a side under 0.8/1.2 strength unable to win a roll at all.
ROLL_LOW = 0.8
ROLL_HIGH = 1.2


def battle_roll(score: float, rng: object = None) -> float:
    import random as _random

    return float(score) * (rng or _random).uniform(ROLL_LOW, ROLL_HIGH)


# Artillery shells dug-in positions: an all-artillery attack ignores this share
# of the defender's entrenchment bonus (scaled by artillery's share of the
# attacker's presence).
ARTILLERY_ENTRENCH_PIERCE = 0.6


def artillery_entrenchment_pierce(
    selected_units_list: list, selected_units: Dict[str, int]
) -> float:
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
    from wars.action_points import (
        entrenchment_defense_multiplier,
        intel_attack_multiplier,
    )

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
        round(base_loser_value * advantage_factor * win_type * MORALE_HIT_FACTOR)
    )
    floor = morale_floor(win_type, loser_units)
    computed_morale_delta = max(floor, computed_morale_delta)
    computed_morale_delta = min(MORALE_DELTA_CAP, computed_morale_delta)
    return computed_morale_delta


# Live master: hit = round(strength terms * 0.1), clamped to 1..200, and a new
# war starts at 100. Most even fights already sit on that floor of 1, so
# shrinking the 0.1 does not make them longer. New wars start at 150 instead
# (1.5x the clock) and a single hit is capped at 24: six attacks, the whole
# starting pool across three branches, deal at most 144 and cannot finish a
# fresh war. The battle roll is unchanged.
MORALE_START = 150
MORALE_HIT_FACTOR = 0.1
MORALE_FLOOR_CLOSE = 1
MORALE_FLOOR_CLEAR = 1
MORALE_FLOOR_CRUSHING = 1
MORALE_FLOOR_EMPTY = 1
MORALE_DELTA_CAP = 24


def morale_floor(win_type: float, loser_units: dict = None) -> int:
    """Minimum morale loss for a battle. Matches master (always 1)."""
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


# Casualty tuning (share of the committed force of each unit type).
# Per-point losses are half the first prototype pass (0.04). A 150-morale
# clock was grinding one branch down to nothing, after which that branch
# sat out and the war idled until the clock ran out. Keeping the armies
# in the field holds the battle rate steady, so hours track battles.
WINNER_LOSS_PER_POINT = 0.02
WINNER_MAX_LOSS_FRAC = 0.30
LOSER_LOSS_PER_POINT = 0.02
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
SUPPORT_FACTOR = 1.15  # phase 3 used 1.3 with the 0.6-1.4 roll
COVER_EFFECT = 0.75
SUPPORT_CAP = 0.6
INTERCEPT_LOSS_MAX = 0.15  # bombers shot down at full fighter cover
FIGHTER_INTERCEPT_LOSS_MAX = 0.08  # intercepting fighters lost at full engagement
AIR_SUPPORT_AP_COST = 2  # air AP, on top of the ground/naval attack's cost


def compute_air_support(
    bombers: int,
    defender_units: Dict[str, int],
    defender_fighters: int,
    attacker_score: float,
    rng: object = None,
) -> Tuple[float, float, int, int]:
    """Return (support_score, cover, bombers_lost, fighters_lost)."""
    import random as _random

    _rng = rng or _random
    bombers = max(0, int(bombers or 0))
    if bombers <= 0:
        return 0.0, 0.0, 0, 0
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
    fighters_lost = 0
    fighters = max(0, int(defender_fighters or 0))
    if cover > 0:
        lost = min(
            bombers,
            int(round(bombers * INTERCEPT_LOSS_MAX * cover * _rng.uniform(0.7, 1.3))),
        )
        # A huge fighter screen does not all die to a handful of bombers:
        # only the share actually tied up in the intercept takes losses.
        engaged = (
            min(1.0, bomber_presence / fighter_presence) if fighter_presence else 0.0
        )
        if fighters and engaged > 0:
            fighters_lost = min(
                fighters,
                int(
                    round(
                        fighters
                        * FIGHTER_INTERCEPT_LOSS_MAX
                        * engaged
                        * _rng.uniform(0.7, 1.3)
                    )
                ),
            )
    return score, cover, lost, fighters_lost


# --- Precision strikes (balance prototype, phase 4) -------------------------
# Cruisers (missiles, naval AP) or bombers (air AP) hit one chosen enemy unit
# type. No territory, loot or morale effect. Cover: destroyers screen against
# missiles, fighters intercept bombers. Anti-spam: per-strike kill cap, halving
# for each earlier strike on the same type in this war (the halving does not
# reset the next day), and a daily limit per war.
PRECISION_STRIKERS = {
    "cruisers": ("naval", "destroyers"),
    "bombers": ("air", "fighters"),
}
PRECISION_TARGETS = (
    "soldiers",
    "tanks",
    "artillery",
    "fighters",
    "bombers",
    "apaches",
    "destroyers",
    "cruisers",
    "submarines",
    "aircraft_carriers",
)
PRECISION_AP_COST = 3
STRIKE_MAX_FRAC = 0.06  # most of the targeted type one strike can kill
STRIKE_REACH = 0.25  # strike power needed (vs target power) for full effect
STRIKE_COVER_EFFECT = 0.7  # full cover removes 70% of the effect
STRIKE_DIMINISH = 0.5  # x0.5 per earlier strike on that type, for the whole war
STRIKE_DAILY_LIMIT = 3  # strikes per attacker per war per 24h
STRIKER_LOSS_MAX = 0.05  # striker losses at full cover
# Disruption shakes the struck type for the striker's next attack that
# actually fields it (within the window). Capped so the type still does
# most of its job: a missile strike cannot make tanks something you ignore.
SUPPRESS_MAX = 0.20
SUPPRESS_WINDOW_HOURS = 3


def max_daily_strike_kill_fraction() -> float:
    """Most of one unit type a full day of strikes can destroy.

    Three strikes, each halving the previous, all at full reach and no cover.
    Earlier strikes in the same war keep counting, so later days are smaller.
    The lifetime sum if you never stopped is STRIKE_MAX_FRAC / (1 - STRIKE_DIMINISH).
    """
    return sum(
        STRIKE_MAX_FRAC * (STRIKE_DIMINISH**i) for i in range(STRIKE_DAILY_LIMIT)
    )


def compute_precision_strike(
    striker, strikers, target_unit, target_amount, cover_amount, prior_hits=0, rng=None
):
    """Pure strike math. Returns dict(killed, lost, cover, frac)."""
    import random as _random

    r = rng or _random
    strikers = max(0, int(strikers or 0))
    target_amount = max(0, int(target_amount or 0))
    if (
        striker not in PRECISION_STRIKERS
        or target_unit not in PRECISION_TARGETS
        or strikers == 0
        or target_amount == 0
    ):
        return {"killed": 0, "lost": 0, "cover": 0.0, "frac": 0.0, "suppress": 0.0}
    power = UNIT_POWER[striker] * strikers
    cover_power = UNIT_POWER[PRECISION_STRIKERS[striker][1]] * max(
        0, int(cover_amount or 0)
    )
    cover = min(1.0, cover_power / power)
    reach = min(1.0, power / (STRIKE_REACH * UNIT_POWER[target_unit] * target_amount))
    raw = (
        STRIKE_MAX_FRAC
        * reach
        * (1 - STRIKE_COVER_EFFECT * cover)
        * (STRIKE_DIMINISH ** max(0, int(prior_hits)))
    )
    # Jitter stays under the pre-roll share, so a full day at perfect reach
    # and no cover cannot exceed max_daily_strike_kill_fraction().
    frac = min(raw, STRIKE_MAX_FRAC) * r.uniform(0.9, 1.1)
    frac = min(frac, raw, STRIKE_MAX_FRAC)
    killed = min(target_amount, int(target_amount * frac))
    suppress = min(SUPPRESS_MAX, SUPPRESS_MAX * (frac / STRIKE_MAX_FRAC))
    lost = min(
        strikers, int(round(strikers * STRIKER_LOSS_MAX * cover * r.uniform(0.7, 1.3)))
    )
    return {
        "killed": killed,
        "lost": lost,
        "cover": cover,
        "frac": frac,
        "suppress": suppress,
    }


def suppression_penalty(defender_units, suppressed):
    """Share of the defender's score removed by disruption.
    suppressed: {unit_type: fraction 0..SUPPRESS_MAX} (summed per type, capped)."""
    total = sum(
        UNIT_POWER.get(u, 0) * max(0, int(a or 0))
        for u, a in (defender_units or {}).items()
    )
    if total <= 0 or not suppressed:
        return 0.0
    pen = 0.0
    for u, f in suppressed.items():
        f = max(0.0, min(SUPPRESS_MAX, float(f or 0)))
        pen += (
            f
            * UNIT_POWER.get(u, 0)
            * max(0, int((defender_units or {}).get(u, 0) or 0))
            / total
        )
    return min(pen, SUPPRESS_MAX)
