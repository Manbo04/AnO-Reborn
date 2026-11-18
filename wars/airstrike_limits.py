"""Strategic airstrike limits (feature flag ``strategic_airstrike_limits``, ships OFF).

Problem (wars/routes.py ``strategic_airstrike``, read from the code): the strike spends
no action points and has no cooldown, so it can be repeated again and again (the
bombers that survive come back). Against a defender without fighters it destroys every
silo, and one strike with about 50 surviving bombers permanently removes the Nuclear
Testing Facility tech. Only the defender's fighters stand in the way.

Flag ON:
  * each strike costs STRATEGIC_AIRSTRIKE_AP_COST air action points, like the drone
    strike (so the existing AP regeneration is the cooldown);
  * one strike destroys at most STRATEGIC_AIRSTRIKE_MAX_SILO_SHARE of the target's silos
    (never fewer than 1, so a strike on a nation with 1 to 3 silos can still land);
  * knocking out the Nuclear Testing Facility tech needs
    STRATEGIC_AIRSTRIKE_TECH_THRESHOLD damage points instead of
    STRATEGIC_AIRSTRIKE_TECH_THRESHOLD_OFF (the tech is still lost for good: making it
    temporary needs a new column, so it is left as a decision for Dede).

Flag OFF: nothing changes. Pure functions, unit tested without a database.
Rollback: switch the flag off at /admin/flags.
"""

from __future__ import annotations

import math

from app_core.feature_flags import is_on

FLAG = "strategic_airstrike_limits"

# --- Tunable numbers (the only place they live) -------------------------------------
STRATEGIC_AIRSTRIKE_AP_COST = 2  # air action points per strike (drone strike: 2)
STRATEGIC_AIRSTRIKE_MAX_SILO_SHARE = 0.25  # most of the target's silos one strike hits
STRATEGIC_AIRSTRIKE_MIN_SILOS_PER_STRIKE = 1  # a strike can always destroy this many
STRATEGIC_AIRSTRIKE_TECH_THRESHOLD = 150  # damage points to destroy the tech (flag on)
STRATEGIC_AIRSTRIKE_TECH_THRESHOLD_OFF = 50  # today's value (flag off)
SILO_DAMAGE_POINTS = 15  # damage points per silo (unchanged, from the route)
# ---------------------------------------------------------------------------------


def enabled(user_id=None) -> bool:
    """True when the limits are on. A flag read never raises: unreadable = off."""
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False


def max_silos_per_strike(
    total_silos: int, max_share: float = STRATEGIC_AIRSTRIKE_MAX_SILO_SHARE
) -> int:
    """Most silos a single strike may destroy."""
    total = max(0, int(total_silos or 0))
    if total == 0:
        return 0
    allowed = int(math.floor(total * float(max_share)))
    return min(total, max(STRATEGIC_AIRSTRIKE_MIN_SILOS_PER_STRIKE, allowed))


def silo_damage_points(
    total_silos: int,
    bombing_power: float,
    threshold: int = SILO_DAMAGE_POINTS,
    max_share: float = STRATEGIC_AIRSTRIKE_MAX_SILO_SHARE,
) -> float:
    """Damage points to hand to apply_building_damage so that at most the allowed
    number of silos fall (``floor(points // threshold)`` silos are destroyed there)."""
    cap_points = max_silos_per_strike(total_silos, max_share) * threshold
    return min(float(bombing_power), float(cap_points))


def tech_threshold(limits_on: bool) -> int:
    """Damage points needed to destroy the Nuclear Testing Facility tech."""
    return (
        STRATEGIC_AIRSTRIKE_TECH_THRESHOLD
        if limits_on
        else STRATEGIC_AIRSTRIKE_TECH_THRESHOLD_OFF
    )
