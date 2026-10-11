"""Citizen Army (defender militia) helpers.

The war supply system was removed (2026-10-11): attacks now cost action
points only and defenders field their whole standing army. This module keeps
the Citizen Army: when the defender has no combat-capable troops in the
attacked domain (none owned or all lost), a citizen militia fights instead.
It can't win the battle, but kills a percentage of every attacking unit type
that was sent. The percentage scales with population and provinces on a
saturating curve (see citizen_army_pct) so it's ~10-20% for a typical
nation and can never exceed CITIZEN_ARMY_MAX_PCT.

Pure functions are kept separate from the DB helper so they can be
unit-tested without a database.
"""

import math
import random
from typing import Dict, Tuple

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


def get_population_and_provinces(db, user_id: int) -> Tuple[int, int]:
    db.execute(
        "SELECT COALESCE(SUM(population), 0), COUNT(id) FROM provinces WHERE userId=%s",
        (user_id,),
    )
    row = db.fetchone()
    if not row:
        return 0, 0
    return int(row[0] or 0), int(row[1] or 0)
