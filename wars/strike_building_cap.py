"""Cap on the share of one building type a drone or cruise missile strike destroys
(feature flag ``strike_building_cap``, ships OFF).

Problem (wars/service.py ``apply_building_damage``, wars/routes.py ``drone_strike`` and
``cruise_missile_strike``): damage is linear (drones 2 points per hit, cruise missiles 8
points per missile, one building per 6, 10 or 15 points) and nothing limits how much of
one building type a single strike can destroy. A big enough swarm removes every farm or
steel mill a nation owns in one strike, and rebuilding costs far more than the strike.

Flag ON: one drone or cruise missile strike destroys at most STRIKE_BUILDING_MAX_SHARE
of the buildings of the chosen type the target owns across all its provinces (never
fewer than STRIKE_BUILDING_MIN_PER_STRIKE, so a strike can always destroy a building
when the target has one). The strategic airstrike has its own limits
(wars/airstrike_limits.py) and population strikes keep their existing 2% cap
(POP_KILL_CAP_PER_STRIKE).

Pure functions, unit tested without a database. Rollback: switch the flag off at
/admin/flags.
"""

from __future__ import annotations

import math

from app_core.feature_flags import is_on

FLAG = "strike_building_cap"

# --- Tunable numbers (the only place they live) -------------------------------------
STRIKE_BUILDING_MAX_SHARE = 0.25  # most of one building type a single strike destroys
STRIKE_BUILDING_MIN_PER_STRIKE = 1  # a strike can always destroy at least this many
# ---------------------------------------------------------------------------------


def enabled(user_id=None) -> bool:
    """True when the cap is on. A flag read never raises: unreadable = off."""
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False


def max_share_for(user_id=None):
    """The share to pass to ``apply_building_damage`` (None = no cap, flag off)."""
    return STRIKE_BUILDING_MAX_SHARE if enabled(user_id) else None


def max_destroyed(total: int, max_share: float = STRIKE_BUILDING_MAX_SHARE) -> int:
    """Most buildings of one type a single strike may destroy when the target owns
    ``total`` of them."""
    total = max(0, int(total or 0))
    if total == 0:
        return 0
    allowed = int(math.floor(total * float(max_share)))
    return min(total, max(STRIKE_BUILDING_MIN_PER_STRIKE, allowed))


def capped_destroyed(total: int, wanted: int, max_share=None) -> int:
    """Buildings destroyed: what the damage points ask for (``wanted``), never more than
    the target owns and, when ``max_share`` is given, never above the share cap."""
    total = max(0, int(total or 0))
    wanted = max(0, int(wanted or 0))
    result = min(total, wanted)
    if max_share is not None:
        result = min(result, max_destroyed(total, max_share))
    return result
