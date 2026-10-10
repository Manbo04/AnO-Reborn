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

    Units whose upkeep resource is depleted (``unusable``) are still on the
    field: they cost no supply and add no combat power (combat_helpers gives
    unusable units zero strength), but they DO take casualties. Before
    2026-10-10 they stayed home, so a defender whose only army was unusable
    fielded nothing, the citizen army fought instead and the real soldiers
    became immune (Kaiser: "won with tanks, enemy lost 0", news 4257).

    Usable units are fielded in full if the budget covers them, otherwise
    every type is scaled down by the same factor, but an owned type never
    drops to 0 (at least 1 always defends).

    Returns (fielded, supply_spent).
    """
    costs = costs or unit_supply_costs()
    unusable = set(unusable or ())
    owned_clean = {u: max(0, int(q or 0)) for u, q in owned.items()}
    usable = {u: q for u, q in owned_clean.items() if u not in unusable}
    idle = {u: q for u, q in owned_clean.items() if u in unusable}

    full_cost = sum(q * costs.get(u, 1) for u, q in usable.items())
    if full_cost <= budget:
        fielded = dict(usable)
    else:
        factor = budget / float(full_cost)
        fielded = {
            u: (max(1, int(math.floor(q * factor))) if q > 0 else 0)
            for u, q in usable.items()
        }
    spent = sum(q * costs.get(u, 1) for u, q in fielded.items())
    fielded.update(idle)
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
