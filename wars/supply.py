"""Defender supply + Citizen Army (war supply asymmetry fix, 2026-09-27).

Design agreed with germanicusjuliuscaesar ("Unknown Identity") in the
#military-recommendations thread (2026-09-16), approved by Dede:

* Before this, only the attacker paid supply (per unit sent, from the war's
  attacker_supplies pool) while the defender fielded its entire standing
  army in the attacked domain for free. Whoever had the bigger stockpile
  always won, so attacking a big nation was never viable.
* Now defense uses the SAME mechanism as attack: every defending unit costs
  its unit supply_cost (units.py), paid from the defending nation's own
  pool on this war. The defender can only field as much of its army as its
  supply covers; if the full army costs more, every unit type is scaled
  down proportionally.
* Flat floor of DEFENDER_SUPPLY_FLOOR (200, the attacker's minimum too):
  defense always has at least 200 supply to work with, and defending never
  pushes the pool below 200. (Counter-attacks launched by the same nation
  still spend normally via Units.save(); if those drained the pool under
  200, defending is simply free at the 200 level and doesn't touch it.)
* Citizen Army: when the defender has no combat-capable troops in the
  attacked domain (none owned, all lost, or all immobilised by an empty
  upkeep resource), a citizen militia fights instead. It uses no supply,
  can't win the battle, but kills a percentage of every attacking unit type
  that was sent. The percentage scales with population and provinces on a
  saturating curve (see citizen_army_pct) so it's ~10-20% for a typical
  nation and can never exceed CITIZEN_ARMY_MAX_PCT.

Pure functions (budget/ration/pct/casualties) are kept separate from the two
DB helpers so they can be unit-tested without a database.
"""

import math
import os
import random
from typing import Dict, Iterable, Optional, Tuple

DEFENDER_SUPPLY_FLOOR = 200

# Citizen Army curve: pct = MIN + (MAX - MIN) * (1 - exp(-score / SOFTNESS))
# with score = population_in_millions + PROVINCE_WEIGHT * provinces.
#   1 province,  1M pop   -> ~5%
#   5 provinces, 10M pop  -> ~10%
#   10 provinces, 30M pop -> ~16%
#   37 provinces, 200M pop -> ~25% (cap)
CITIZEN_ARMY_MIN_PCT = 0.04
CITIZEN_ARMY_MAX_PCT = 0.25
CITIZEN_ARMY_SOFTNESS = 60.0
CITIZEN_ARMY_PROVINCE_WEIGHT = 2.0
# Per-battle variance on the citizen army's damage (still clamped to MAX).
CITIZEN_ARMY_VARIANCE = (0.85, 1.15)


def unit_supply_costs() -> Dict[str, int]:
    """unit name -> supply cost per unit, straight from units.py so attack
    and defense can never disagree about what a unit costs."""
    from units import Units

    return {iface.unit_type: int(iface.supply_cost) for iface in Units.allUnitInterfaces}


# ---------------------------------------------------------------------------
# Army-scaled supply (2026-10-04, ivegottogodosomething / DNS feedback)
#
# A flat 2000 cap meant no attack could ever use more than ~2000 infantry or
# 400 tanks, so building past that was pointless. Each side's cap on a war
# now scales with the supply value of its conventional army, the pool fills
# in about SUPPLY_FILL_HOURS, and the war opens in the defender's favour:
# the attacker starts mobilising from a small share of its cap while the
# defender starts half-stocked.
# ---------------------------------------------------------------------------

# Only units that fight in the ground/air/naval domains count toward the cap
# (missiles, nukes, spies and SAMs have their own paths).
CONVENTIONAL_UNITS = (
    "soldiers", "tanks", "artillery",
    "destroyers", "cruisers", "submarines",
    "fighters", "bombers", "apaches",
)
# Same env knob the hourly refill uses (app_core/game_ticks/maintenance.py).
SUPPLY_CAP_MIN = int(os.getenv("WAR_SUPPLY_CAP", "2000"))
SUPPLY_CAP_ARMY_SHARE = 0.25
SUPPLY_FILL_HOURS = 24
ATTACKER_START_SHARE = 0.2
DEFENDER_START_SHARE = 0.5


def army_supply_value(units: Dict[str, int], costs: Optional[Dict[str, int]] = None) -> int:
    """Supply it would cost to send every conventional unit at once."""
    costs = costs or unit_supply_costs()
    return int(
        sum(
            max(0, int(units.get(u, 0) or 0)) * costs.get(u, 1)
            for u in CONVENTIONAL_UNITS
        )
    )


def supply_cap(army_value: int, base_cap: int = SUPPLY_CAP_MIN) -> int:
    return max(int(base_cap), int(round((army_value or 0) * SUPPLY_CAP_ARMY_SHARE)))


def hourly_regen(cap: int, base_regen: int = 0, bonus: float = 1.0) -> int:
    """Per-hour refill: enough to fill the cap in SUPPLY_FILL_HOURS."""
    per_hour = max(int(base_regen), int(math.ceil(cap / float(SUPPLY_FILL_HOURS))))
    return int(round(per_hour * bonus))


def starting_supplies(attacker_cap: int, defender_cap: int) -> Tuple[int, int]:
    return (
        max(DEFENDER_SUPPLY_FLOOR, int(round(attacker_cap * ATTACKER_START_SHARE))),
        max(DEFENDER_SUPPLY_FLOOR, int(round(defender_cap * DEFENDER_START_SHARE))),
    )


def get_army_supply_values(db, user_ids: Iterable[int]) -> Dict[int, int]:
    """user_id -> army_supply_value, one query for any number of users."""
    ids = sorted({int(u) for u in user_ids if u is not None})
    if not ids:
        return {}
    db.execute(
        """
        SELECT um.user_id, LOWER(ud.name), COALESCE(um.quantity, 0)
        FROM user_military um
        JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE um.user_id = ANY(%s) AND LOWER(ud.name) = ANY(%s)
        """,
        (ids, list(CONVENTIONAL_UNITS)),
    )
    per_user: Dict[int, Dict[str, int]] = {u: {} for u in ids}
    for row in db.fetchall():
        uid, name, qty = row[0], row[1], row[2]
        per_user.setdefault(uid, {})[name] = per_user.get(uid, {}).get(name, 0) + int(qty or 0)
    costs = unit_supply_costs()
    return {u: army_supply_value(units, costs) for u, units in per_user.items()}


def get_supply_caps(db, user_ids: Iterable[int]) -> Dict[int, int]:
    return {u: supply_cap(v) for u, v in get_army_supply_values(db, user_ids).items()}


def seed_starting_supplies(db, war_id, attacker_id: int, defender_id: int) -> None:
    """Set a new war's opening pools from both sides' army-scaled caps."""
    if not war_id:
        return
    caps = get_supply_caps(db, (attacker_id, defender_id))
    atk, dfn = starting_supplies(
        caps.get(attacker_id, SUPPLY_CAP_MIN), caps.get(defender_id, SUPPLY_CAP_MIN)
    )
    db.execute(
        "UPDATE wars SET attacker_supplies=%s, defender_supplies=%s WHERE id=%s",
        (atk, dfn, war_id),
    )


def defense_supply_budget(pool: Optional[int]) -> int:
    """Supply available to defend with: the pool, but never less than the floor."""
    try:
        pool = int(pool or 0)
    except (TypeError, ValueError):
        pool = 0
    return max(pool, DEFENDER_SUPPLY_FLOOR)


def pool_after_defense(pool: int, spend: int) -> int:
    """New pool value after spending `spend` on defense. Defense can only
    consume supply above the floor; a pool already under the floor is left
    as-is. Mirrors the SQL in spend_defense_supplies()."""
    pool = int(pool or 0)
    spend = max(0, int(spend or 0))
    return max(min(pool, DEFENDER_SUPPLY_FLOOR), pool - spend)


def ration_defenders(
    owned: Dict[str, int],
    budget: int,
    costs: Optional[Dict[str, int]] = None,
    unusable: Iterable[str] = (),
) -> Tuple[Dict[str, int], int]:
    """Decide how many of each owned unit type actually defends.

    Units whose upkeep resource is depleted (``unusable``) stay home: they
    contribute nothing in combat anyway, so they neither cost supply nor
    take casualties. The rest are fielded in full if the budget covers
    them, otherwise every type is scaled down by the same factor.

    Returns (fielded, supply_spent).
    """
    costs = costs or unit_supply_costs()
    unusable = set(unusable or ())
    usable = {
        u: max(0, int(q or 0)) if u not in unusable else 0 for u, q in owned.items()
    }
    full_cost = sum(q * costs.get(u, 1) for u, q in usable.items())
    if full_cost <= budget:
        return dict(usable), int(full_cost)

    factor = budget / float(full_cost)
    fielded = {u: int(math.floor(q * factor)) for u, q in usable.items()}
    spent = sum(q * costs.get(u, 1) for u, q in fielded.items())
    return fielded, int(spent)


def citizen_army_pct(population: int, provinces: int) -> float:
    """Deterministic share of the attacking force the citizen army destroys."""
    pop_m = max(0.0, float(population or 0)) / 1_000_000.0
    score = pop_m + CITIZEN_ARMY_PROVINCE_WEIGHT * max(0, int(provinces or 0))
    span = CITIZEN_ARMY_MAX_PCT - CITIZEN_ARMY_MIN_PCT
    pct = CITIZEN_ARMY_MIN_PCT + span * (1.0 - math.exp(-score / CITIZEN_ARMY_SOFTNESS))
    return min(CITIZEN_ARMY_MAX_PCT, pct)


def citizen_army_losses(
    attacker_sent: Dict[str, int], pct: float, rng=None
) -> Dict[str, int]:
    """Attacker casualties inflicted by the citizen army, per unit type sent.
    Never exceeds the amount sent nor CITIZEN_ARMY_MAX_PCT of it."""
    rng = rng or random
    roll = pct * rng.uniform(*CITIZEN_ARMY_VARIANCE)
    roll = max(0.0, min(CITIZEN_ARMY_MAX_PCT, roll))
    losses = {}
    for unit, sent in (attacker_sent or {}).items():
        sent = max(0, int(sent or 0))
        if sent <= 0:
            continue
        losses[unit] = min(sent, int(math.floor(sent * roll)))
    return losses


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def supply_column_for(db, war_id: int, user_id: int) -> Optional[str]:
    """Which wars.*_supplies column belongs to user_id on this war."""
    db.execute("SELECT attacker, defender FROM wars WHERE id=%s", (war_id,))
    row = db.fetchone()
    if not row:
        return None
    if user_id == row[0]:
        return "attacker_supplies"
    if user_id == row[1]:
        return "defender_supplies"
    return None


def read_supply_pool(db, war_id: int, user_id: int) -> int:
    col = supply_column_for(db, war_id, user_id)
    if not col:
        return 0
    db.execute(f"SELECT COALESCE({col}, 0) FROM wars WHERE id=%s", (war_id,))
    row = db.fetchone()
    return int(row[0] or 0) if row else 0


def spend_defense_supplies(db, war_id: int, user_id: int, spend: int) -> Optional[int]:
    """Atomically deduct defense supply with the floor rule. Returns the new
    pool value (or None if user_id isn't on this war). A single UPDATE, so a
    concurrent counter-attack deduction can't race it into a wrong value."""
    col = supply_column_for(db, war_id, user_id)
    if not col or not spend:
        return read_supply_pool(db, war_id, user_id) if col else None
    db.execute(
        f"UPDATE wars SET {col} = GREATEST(LEAST({col}, %s), {col} - %s) "
        f"WHERE id=%s RETURNING {col}",
        (DEFENDER_SUPPLY_FLOOR, int(spend), war_id),
    )
    row = db.fetchone()
    return int(row[0]) if row else None


def get_population_and_provinces(db, user_id: int) -> Tuple[int, int]:
    db.execute(
        "SELECT COALESCE(SUM(population), 0), COUNT(id) FROM provinces WHERE userId=%s",
        (user_id,),
    )
    row = db.fetchone()
    if not row:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)
