"""Who can nuke whom (feature flag ``nuke_target_rules``, ships OFF).

Problem (Dede, 2026-11): nukes are one-click, most of the damage lands on nations that
could never answer, and nothing is rechecked when the missile is launched. These are the
SAFE rules that need no new table:

  a) RANGE at launch time. The target must be inside the population war range
     (75% to 133% of the launcher's population strength, wars/war_range.py) when
     the nuke is fired, not only when the war was declared.
  b) PROTECTION. A target under NUKE_PROTECTION_MIN_INFLUENCE influence, or whose
     account is younger than NUKE_PROTECTION_MIN_AGE_DAYS days, cannot be nuked.
  c) RETALIATION. Always allowed against the nation that nuked you in this war
     (wars.nuclear.is_retaliation); it skips (a) and (b).

NOT built here (design only, docs/design/NUKE_TARGET_RULES.md): the 7 day average score
band, which needs a daily influence table and a tick.

Where it applies: wars.nuclear.plan_strike, for single strikes and for the up-front gate
of a Fire All salvo (execute_salvo calls plan_strike once). Warheads inside a salvo are
NOT rechecked: the first warhead kills people, which can push the target out of range
mid-salvo, and the salvo was allowed when it was fired.

Flag OFF: nothing changes. Everything below ``can_nuke`` is a thin database reader; the
rules live in the pure ``can_nuke`` so they are unit tested without a database.
Rollback: switch the flag off at /admin/flags.
"""

from __future__ import annotations

import datetime
from typing import Optional, Tuple

from app_core.feature_flags import is_on
from wars.war_range import (
    WAR_RANGE_HIGH,
    WAR_RANGE_LOW,
    format_war_range_error,
    get_user_war_strength,
    in_war_range,
)

FLAG = "nuke_target_rules"

# --- Tunable numbers (the only place they live) -------------------------------------
NUKE_PROTECTION_MIN_INFLUENCE = 100_000  # a target below this cannot be nuked
NUKE_PROTECTION_MIN_AGE_DAYS = 14  # a target account younger than this is protected
# The war range itself (75% to 133%) is WAR_RANGE_LOW / WAR_RANGE_HIGH in
# wars/war_range.py and is reused, not copied, so a change there applies to nukes too.
# ---------------------------------------------------------------------------------


def enabled(user_id=None) -> bool:
    """True when the rules are on. A flag read never raises: unreadable = off."""
    try:
        return is_on(FLAG, user_id)
    except Exception:
        return False


def account_age_days(
    date_str, today: Optional[datetime.date] = None
) -> Optional[float]:
    """Age in days of an account from ``users.date`` (a 'YYYY-MM-DD' string). None when
    the value is missing or cannot be read (the caller then does not protect)."""
    if not date_str:
        return None
    try:
        created = datetime.date.fromisoformat(str(date_str).strip()[:10])
    except ValueError:
        return None
    today = today or datetime.date.today()
    return float((today - created).days)


def can_nuke(
    attacker_strength: float,
    target_strength: float,
    target_influence: float,
    target_age_days: Optional[float],
    is_retaliation: bool,
) -> Tuple[bool, Optional[str]]:
    """Return (ok, reason). ``reason`` is a player-facing sentence when ok is False.

    Strengths are population strengths (wars.war_range.war_strength). Retaliation
    against the nation that nuked you is always allowed. An unknown account age does
    not protect.
    """
    if is_retaliation:
        return True, None
    influence = int(target_influence or 0)
    if influence < NUKE_PROTECTION_MIN_INFLUENCE:
        return False, (
            "That nation is protected from nuclear strikes: it needs at least "
            f"{NUKE_PROTECTION_MIN_INFLUENCE:,} influence (it has {influence:,})."
        )
    if target_age_days is not None and target_age_days < NUKE_PROTECTION_MIN_AGE_DAYS:
        return False, (
            "That nation is protected from nuclear strikes: its account is younger "
            f"than {NUKE_PROTECTION_MIN_AGE_DAYS} days."
        )
    if not in_war_range(attacker_strength, target_strength):
        return False, (
            format_war_range_error(attacker_strength)
            + " A nuke can only be launched at a nation inside your war range "
            f"({WAR_RANGE_LOW:.0%} to {WAR_RANGE_HIGH:.0%} of your population "
            "strength)."
        )
    return True, None


def check(db, attacker_id: int, enemy_id: int, retaliation: bool) -> Optional[str]:
    """Read the numbers and apply ``can_nuke``. Returns the refusal text, or None when
    the launch is allowed. Retaliation does not touch the database at all."""
    if retaliation:
        return None
    from wars.nuclear import fresh_influence

    attacker_strength = get_user_war_strength(db, attacker_id)
    target_strength = get_user_war_strength(db, enemy_id)
    influence = fresh_influence(db, enemy_id)
    db.execute("SELECT date FROM users WHERE id = %s", (enemy_id,))
    row = db.fetchone()
    age = account_age_days(row[0] if row else None)
    ok, reason = can_nuke(attacker_strength, target_strength, influence, age, False)
    return None if ok else reason
