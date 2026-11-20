"""ICBM unit-destruction limits (feature flag ``icbm_damage_limits``, ships OFF).

Problem: an ICBM strike is resolved by ``Military.special_fight``
(attack_scripts/Nations.py), not by the normal fight path. The units it destroys are

    destruction_rate * (damage / (1 + bonus)) * fired

where ``damage`` is ``IcbmUnit.damage * fired`` (units.py), so the number fired is
multiplied in TWICE and the loss grows with the square of the number fired. Nothing
limits how much of one unit type a strike can destroy except what the target owns, so a
couple of missiles wipe a whole fleet ("2 ICBMs took out my 50 destroyers").

Flag ON (both changes together):
  (a) growth is linear: the number fired is multiplied in once, not twice;
  (b) one strike destroys at most ICBM_MAX_UNIT_SHARE of the target's units of the
      chosen type (measured on what the target owns before the strike), but never
      less than what ONE missile would destroy: the cap is
      max(share, one missile's own damage), so a single ICBM is not weakened and only
      the extra missiles of a barrage are limited (same rule as the nuke salvo cap).
  Also: the divisor ``1 + bonus`` never drops below ICBM_MIN_DIVISOR. IcbmUnit.attack
  gives a NEGATIVE bonus against submarines (-5 per missile), which makes the
  divisor negative and the destruction negative, so a strike would ADD submarines
  (see tests/test_icbm_damage.py). With the flag on a strike never adds units.

Only ICBMs use this (nukes and every other fight are untouched). Iron Dome interception
still scales the damage down first. Everything here is pure so it is unit tested without
a database. Rollback: switch the flag off at /admin/flags.
"""

from __future__ import annotations

from app_core.feature_flags import is_on

FLAG = "icbm_damage_limits"

# --- Tunable numbers (the only place they live) -------------------------------------
ICBM_MAX_UNIT_SHARE = 0.25  # share of one unit type a strike may destroy (a lone
# missile keeps its full effect: cap = max(share, one missile's own damage))
ICBM_MIN_DIVISOR = 1.0  # floor for (1 + bonus); stops negative destruction
# ---------------------------------------------------------------------------------


def enabled(user_id=None) -> bool:
    """True when the ICBM limits are on. A flag read never raises: unreadable = off."""
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False


def legacy_destruction(damage: float, bonus: float, fired: int, rate: float) -> float:
    """Today's formula (flag off), exactly as special_fight computes it.
    ``damage`` is attack_effects[0] (already ``unit damage * fired``)."""
    return rate * (damage / (1 + bonus) * fired)


def limited_destruction(
    damage: float,
    bonus: float,
    fired: int,
    rate: float,
    target_amount: int,
    surviving: float = 1.0,
    max_share: float = ICBM_MAX_UNIT_SHARE,
) -> float:
    """Units destroyed with the flag on: linear in ``fired``, never negative, and at
    most ``max(max_share of what the target owns, what ONE missile would destroy)``.
    The second term means a single ICBM is never weakened (it does what it does today),
    the same rule the nuke salvo cap uses; only extra missiles are limited.
    ``surviving`` is the share of the missiles the Iron Domes did not shoot down
    (1.0 = none intercepted)."""
    if fired <= 0 or target_amount <= 0:
        return 0.0
    divisor = max(ICBM_MIN_DIVISOR, 1 + bonus)
    # ``damage`` already contains ``fired`` once, so no second multiplication.
    raw = max(0.0, rate * damage / divisor) * max(0.0, min(1.0, surviving))
    # what one missile of this strike would destroy (bonus also scales with ``fired``)
    single = max(
        0.0, rate * (damage / fired) / max(ICBM_MIN_DIVISOR, 1 + bonus / fired)
    )
    cap = max(max_share * int(target_amount), single)
    return min(raw, cap)
