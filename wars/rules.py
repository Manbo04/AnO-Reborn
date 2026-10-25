"""War rules overhaul (2026-10-25): tunable values and pure helpers.

* **Surrender** needs both sides: the losing side offers a conditional or
  unconditional surrender, the other side accepts (or rejects) it.
  - Conditional: the war ends, the winner takes reduced spoils
    (CONDITIONAL_SURRENDER_SPOILS), no further penalty.
  - Unconditional: full war spoils plus a temporary military cap -- the
    surrendering nation's manpower cap is multiplied by
    UNCONDITIONAL_SURRENDER_MANPOWER_FACTOR for
    UNCONDITIONAL_SURRENDER_PENALTY_SECONDS (stored in war_penalties).
* **Minimum war duration.** No war can be ended by peace or surrender
  before WAR_MIN_DURATION_SECONDS (morale reaching zero still ends it).
* **Post-war cooldowns.** After a war ends the aggressor can't re-declare on
  the same nation for TRUCE_SECONDS and the defender can't strike back for
  DEFENDER_COOLDOWN_SECONDS.
* **Allies (MDP).** Joining needs war range (no unlimited range), an ongoing
  war, and no active truce. A join is recorded with origin 'mdp_join': it is
  a counter-attack, not an offensive war, so the original aggressor stays
  the aggressor of record. The aggressor's own allies can counter the joiner
  only when the joiner is inside their war range.
* **Nukes.** One nuke volley per side per war (MAX_NUKE_VOLLEYS_PER_WAR);
  radiation's short-term effects are scaled by RADIATION_DAMAGE_MULTIPLIER.
"""
from __future__ import annotations

HOUR = 3600
DAY = 24 * HOUR

WAR_MIN_DURATION_SECONDS = 24 * HOUR
TRUCE_SECONDS = 3 * DAY
DEFENDER_COOLDOWN_SECONDS = 24 * HOUR

SURRENDER_KINDS = ("conditional", "unconditional")
CONDITIONAL_SURRENDER_SPOILS = 0.10  # share of each resource (standard: 20%)
UNCONDITIONAL_SURRENDER_MANPOWER_FACTOR = 0.5
UNCONDITIONAL_SURRENDER_PENALTY_SECONDS = 5 * DAY
PENALTY_MANPOWER_CAP = "manpower_cap"

WAR_ORIGIN_DECLARED = "declared"
WAR_ORIGIN_MDP_JOIN = "mdp_join"

MAX_NUKE_VOLLEYS_PER_WAR = 1
RADIATION_DAMAGE_MULTIPLIER = 0.5


def war_age_ok(start_date, now) -> bool:
    """True once a war has run long enough to be ended by agreement."""
    if not start_date:
        return True
    return float(now) - float(start_date) >= WAR_MIN_DURATION_SECONDS


def min_duration_error(start_date, now) -> str:
    left = max(0, WAR_MIN_DURATION_SECONDS - (float(now) - float(start_date or now)))
    hours = left / HOUR
    return (
        f"Wars must last at least {WAR_MIN_DURATION_SECONDS // HOUR} hours before "
        f"they can end by peace or surrender ({hours:.1f}h left)."
    )


def aggressor_of(attacker, defender, origin) -> int:
    """Aggressor of record. An MDP join row has the ally as `attacker`, but
    it is a counter-attack: the original aggressor (row defender) remains
    the aggressor."""
    return defender if origin == WAR_ORIGIN_MDP_JOIN else attacker


def post_war_lock_seconds(
    would_be_attacker, last_attacker, last_defender, origin
) -> int:
    """How long after the last war between two nations `would_be_attacker`
    has to wait before declaring on the other."""
    if would_be_attacker == aggressor_of(last_attacker, last_defender, origin):
        return TRUCE_SECONDS
    return DEFENDER_COOLDOWN_SECONDS


def penalized_manpower_cap(cap: int, factors) -> int:
    """Apply every active manpower-cap penalty factor (they don't stack:
    the harshest one wins)."""
    factors = [float(f) for f in (factors or []) if f is not None]
    if not factors:
        return int(cap)
    return max(0, int(int(cap) * min(factors)))


def surrender_spoils_rate(kind, standard_rate):
    return CONDITIONAL_SURRENDER_SPOILS if kind == "conditional" else standard_rate


def nuke_column(war_attacker, user_id) -> str:
    return "attacker_nuked" if user_id == war_attacker else "defender_nuked"
