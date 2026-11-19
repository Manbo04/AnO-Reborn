"""Limits on how many buildings one drone or cruise missile strike destroys
(feature flag ``strike_building_cap``, ships OFF).

Problem (wars/service.py ``apply_building_damage``, wars/routes.py ``drone_strike`` and
``cruise_missile_strike``): damage is linear (drones 2 points per hit, cruise missiles 8
points per missile, one building per 6, 10 or 15 points) and nothing limits how much one
strike destroys. 1,000 drones cost 3,500,000 gold to activate and can destroy 233 farms
that cost 349,500,000 gold to rebuild (100 to 1); against silos (350,000,000 gold each)
the gap is far larger. A share cap alone does not fix that when the target owns a big
stack, so the flag now applies FOUR limits. One strike destroys the smallest of:

  1. what the damage points ask for (unchanged);
  2. SHARE: at most STRIKE_BUILDING_MAX_SHARE of the building type the target owns
     (STRIKE_SILO_MAX_SHARE for silos), nation-wide, and at least
     STRIKE_BUILDING_MIN_PER_STRIKE on a first strike so a tiny stock can still be hit;
  3. WINDOW: the same share also bounds everything destroyed by strikes in any
     STRIKE_WINDOW_HOURS window, so repeated strikes cannot erode a type. The recent
     total is read from ``war_building_losses`` (source 'strike'); no new table;
  4. VALUE: buildings worth at most STRIKE_VALUE_CAP_MULTIPLE times the activation gold
     of the units committed (variables.MILDICT price x units sent, before any
     interception), valued at the gold price a player pays to rebuild them
     (app_core/economy/building_costs.py ``get_build_cost``, no policy discount).

The strategic airstrike has its own limits (wars/airstrike_limits.py) and population
strikes keep their existing 2% cap (POP_KILL_CAP_PER_STRIKE). One flag, not two: the
share cap alone leaves the cost gap open, so shipping it alone would be a half fix.
Every part is a named constant below.

Pure functions, unit tested without a database. Rollback: switch the flag off at
/admin/flags.
"""

from __future__ import annotations

import math
from typing import NamedTuple, Optional

from app_core.feature_flags import is_on

FLAG = "strike_building_cap"

# --- Tunable numbers (the only place they live) -------------------------------------
STRIKE_BUILDING_MAX_SHARE = 0.25  # most of one building type strikes destroy per window
STRIKE_SILO_MAX_SHARE = 0.10  # the same for silos (about 350,000,000 gold each)
STRIKE_BUILDING_MIN_PER_STRIKE = 1  # a first strike can always destroy this many
STRIKE_WINDOW_HOURS = 72  # window for the cumulative share cap
STRIKE_VALUE_CAP_MULTIPLE = (
    20  # gold of buildings destroyed per gold of units committed
)
# ---------------------------------------------------------------------------------


class StrikeLimits(NamedTuple):
    """What one strike on one building type is allowed to destroy (flag ON)."""

    share: float  # share of the type, per window
    recent_lost: int  # destroyed by strikes in the last STRIKE_WINDOW_HOURS
    max_by_value: Optional[int]  # most the value cap allows (None = not applied)


def enabled(user_id=None) -> bool:
    """True when the limits are on. A flag read never raises: unreadable = off."""
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False


def share_for(building: str) -> float:
    """Share of a building type strikes may destroy per window."""
    return STRIKE_SILO_MAX_SHARE if building == "silos" else STRIKE_BUILDING_MAX_SHARE


def max_by_share(total: int, share: float, recent_lost: int = 0) -> int:
    """Most buildings a strike may destroy under the share and window caps.

    The window cap is ``share`` of what the target had at the start of the window
    (owned now plus destroyed by strikes in the window) minus what was already
    destroyed. The first strike in a window gets at least STRIKE_BUILDING_MIN_PER_STRIKE
    so a stock of 1 to 3 can still be hit.
    """
    total = max(0, int(total or 0))
    recent_lost = max(0, int(recent_lost or 0))
    if total == 0:
        return 0
    allowed = int(math.floor((total + recent_lost) * float(share))) - recent_lost
    if recent_lost == 0:
        allowed = max(STRIKE_BUILDING_MIN_PER_STRIKE, allowed)
    return max(0, min(total, allowed))


def max_by_value(
    activation_gold: float,
    building_gold: float,
    multiple: float = STRIKE_VALUE_CAP_MULTIPLE,
) -> Optional[int]:
    """Most buildings whose rebuild gold fits ``multiple`` x the activation gold of the
    units committed. None when either price is unknown (the value cap is not applied).
    """
    if not activation_gold or not building_gold or building_gold <= 0:
        return None
    return int(
        math.floor(float(multiple) * float(activation_gold) / float(building_gold))
    )


def capped_destroyed(
    total: int, wanted: int, limits: Optional[StrikeLimits] = None
) -> int:
    """Buildings destroyed: what the damage points ask for (``wanted``), never more than
    the target owns and, when ``limits`` is given (flag on), never above the share,
    window or value caps."""
    total = max(0, int(total or 0))
    result = min(total, max(0, int(wanted or 0)))
    if limits is None:
        return result
    result = min(result, max_by_share(total, limits.share, limits.recent_lost))
    if limits.max_by_value is not None:
        result = min(result, max(0, int(limits.max_by_value)))
    return result


def building_gold(building: str) -> Optional[int]:
    """Gold a player pays to build one ``building`` (the game's own price path, without
    the victim's policy discount). None if the building has no price."""
    try:
        from app_core.economy.building_costs import get_build_cost

        return int(get_build_cost(building)["gold"])
    except Exception:
        return None


def unit_activation_gold(unit: str, count: int) -> int:
    """Gold it costs to activate ``count`` of a stockpile unit (variables.MILDICT)."""
    import variables

    return int(variables.MILDICT.get(unit, {}).get("price", 0) or 0) * max(
        0, int(count)
    )


def recent_strike_losses(db, victim_id: int, building: str) -> int:
    """Buildings of this type the victim lost to strikes in the last window, from the
    war history log (``war_building_losses``). The log is best effort: it is skipped if
    the insert ever fails, in which case this undercounts."""
    try:
        db.execute("SAVEPOINT strike_recent_losses")
        db.execute(
            "SELECT COALESCE(SUM(quantity), 0) FROM war_building_losses "
            "WHERE victim_id = %s AND building = %s AND source = 'strike' "
            "AND created_at > now() - make_interval(hours => %s)",
            (victim_id, str(building), STRIKE_WINDOW_HOURS),
        )
        row = db.fetchone()
        db.execute("RELEASE SAVEPOINT strike_recent_losses")
        return int(row[0] or 0) if row else 0
    except Exception:
        try:
            db.execute("ROLLBACK TO SAVEPOINT strike_recent_losses")
        except Exception:
            pass
        return 0


def limits_for(
    db, user_id, victim_id: int, building: str, unit: str, units_sent: int
) -> Optional[StrikeLimits]:
    """The limits to pass to ``apply_building_damage``; None when the flag is off (the
    old behaviour, and no extra queries)."""
    if not enabled(user_id):
        return None
    return StrikeLimits(
        share=share_for(building),
        recent_lost=recent_strike_losses(db, victim_id, building),
        max_by_value=max_by_value(
            unit_activation_gold(unit, units_sent), building_gold(building) or 0
        ),
    )
