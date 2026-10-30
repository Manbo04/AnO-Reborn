"""Vacation mode: a player-controlled shield for when life gets busy.

Rules (anti-abuse):
  * can only be switched on with no ongoing wars;
  * while on, the nation can't be targeted by war declarations and can't
    declare war, attack, send spies or buy military;
  * it stays on for at least MIN_VACATION_HOURS;
  * after switching off, COOLDOWN_DAYS pass before it can be switched on again.
The economy keeps ticking normally.

Every read tolerates the users.vacation_* columns not being migrated yet
(treated as "not on vacation") so a deploy can't break the game ahead of the
migration.
"""
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import session

MIN_VACATION_HOURS = 72
COOLDOWN_DAYS = 7
# Durations a player can pick when switching vacation on (days). It ends on
# its own when the chosen time is up; it can still be switched off early once
# MIN_VACATION_HOURS have passed.
DURATION_CHOICES_DAYS = (3, 7, 14, 30)
DEFAULT_DURATION_DAYS = 7


def parse_duration_days(raw):
    """Validated duration in days, or None if it isn't one of the choices."""
    try:
        days = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return days if days in DURATION_CHOICES_DAYS else None


def _effective(on, ended, until, now):
    """(on, ended_at) after applying an elapsed chosen duration."""
    if on and until is not None and now >= until:
        return False, until
    return on, ended

ON_VACATION_ATTACKER_MSG = (
    "You're on vacation. Turn vacation mode off in Settings to declare war, "
    "attack, spy or buy military."
)
ON_VACATION_DEFENDER_MSG = (
    "That nation is on vacation and can't be attacked right now."
)


def _now():
    return datetime.now(timezone.utc)


def _aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _optional_fetch(db, sql, params):
    """Run a read inside a SAVEPOINT so a missing column never aborts the
    caller's transaction. Returns None on failure."""
    try:
        db.execute("SAVEPOINT vacation_optional_read")
    except Exception:
        return None
    try:
        db.execute(sql, params)
        row = db.fetchone()
        db.execute("RELEASE SAVEPOINT vacation_optional_read")
        return row
    except Exception:
        try:
            db.execute("ROLLBACK TO SAVEPOINT vacation_optional_read")
        except Exception:
            pass
        return None


def is_on_vacation(db, user_id, lock=False) -> bool:
    """Is this nation on vacation? `lock=True` takes a row share lock so a
    concurrent enable can't slip between this check and the caller's write."""
    row = _optional_fetch(
        db,
        "SELECT vacation_mode AND (vacation_until IS NULL OR vacation_until > NOW()) "
        "FROM users WHERE id=%s"
        + (" FOR SHARE" if lock else ""),
        (user_id,),
    )
    return bool(row and row[0])


def get_vacation_state(db, user_id, now=None) -> dict:
    """Everything the settings page needs: on/off and when each change is allowed."""
    now = now or _now()
    state = {
        "available": False,
        "on": False,
        "started_at": None,
        "can_disable_at": None,
        "can_enable_at": None,
        "until": None,
        "duration_choices": DURATION_CHOICES_DAYS,
        "default_duration": DEFAULT_DURATION_DAYS,
    }
    row = _optional_fetch(
        db,
        "SELECT vacation_mode, vacation_started_at, vacation_ended_at, vacation_until "
        "FROM users WHERE id=%s",
        (user_id,),
    )
    if not row:
        return state
    until = _aware(row[3])
    on, ended = _effective(bool(row[0]), _aware(row[2]), until, now)
    started = _aware(row[1])
    state["available"] = True
    state["until"] = until if on else None
    state["on"] = on
    state["started_at"] = started
    if on and started:
        until = started + timedelta(hours=MIN_VACATION_HOURS)
        state["can_disable_at"] = until if until > now else None
    elif not on and ended:
        until = ended + timedelta(days=COOLDOWN_DAYS)
        state["can_enable_at"] = until if until > now else None
    return state


def _fmt_wait(delta) -> str:
    minutes = max(1, int(delta.total_seconds() // 60))
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        days, hours = divmod(hours, 24)
        return f"{days}d {hours}h"
    return f"{hours}h {mins}m" if hours else f"{mins}m"


def enable_vacation(db, user_id, now=None, days=DEFAULT_DURATION_DAYS):
    """Switch vacation on for `days` days. Returns (ok, message)."""
    now = now or _now()
    if days not in DURATION_CHOICES_DAYS:
        return False, "Pick how long your vacation should last."
    row = _optional_fetch(
        db,
        "SELECT vacation_mode, vacation_started_at, vacation_ended_at, vacation_until "
        "FROM users WHERE id=%s FOR UPDATE",
        (user_id,),
    )
    if row is None:
        return False, "Vacation mode isn't available yet. Try again shortly."
    on, ended = _effective(bool(row[0]), _aware(row[2]), _aware(row[3]), now)
    if on:
        return False, "You're already on vacation."
    if ended and now < ended + timedelta(days=COOLDOWN_DAYS):
        wait = _fmt_wait(ended + timedelta(days=COOLDOWN_DAYS) - now)
        return False, f"Vacation mode is on cooldown for another {wait}."
    # The row lock above serializes with declare_war's FOR SHARE vacation
    # check, so a war can't be created between this check and the UPDATE.
    db.execute(
        "SELECT 1 FROM wars WHERE (attacker=%s OR defender=%s) "
        "AND peace_date IS NULL LIMIT 1",
        (user_id, user_id),
    )
    if db.fetchone():
        return False, "You can't go on vacation while you're at war."
    db.execute(
        "UPDATE users SET vacation_mode=TRUE, vacation_started_at=%s, "
        "vacation_until=%s, vacation_ended_at=NULL WHERE id=%s",
        (now, now + timedelta(days=days), user_id),
    )
    return True, (
        f"Vacation mode is on for {days} days. You can switch it off early "
        f"after {MIN_VACATION_HOURS} hours."
    )


def disable_vacation(db, user_id, now=None):
    """Switch vacation off once the minimum stay is over. Returns (ok, message)."""
    now = now or _now()
    row = _optional_fetch(
        db,
        "SELECT vacation_mode, vacation_started_at, vacation_until FROM users "
        "WHERE id=%s FOR UPDATE",
        (user_id,),
    )
    if row is None:
        return False, "Vacation mode isn't available yet. Try again shortly."
    on, _ended = _effective(bool(row[0]), None, _aware(row[2]), now)
    started = _aware(row[1])
    if not on:
        return False, "You're not on vacation."
    if started and now < started + timedelta(hours=MIN_VACATION_HOURS):
        wait = _fmt_wait(started + timedelta(hours=MIN_VACATION_HOURS) - now)
        return False, f"Vacation mode must stay on for {wait} more."
    db.execute(
        "UPDATE users SET vacation_mode=FALSE, vacation_ended_at=%s, vacation_until=NULL "
        "WHERE id=%s",
        (now, user_id),
    )
    return True, (
        f"Vacation mode is off. You can turn it on again in {COOLDOWN_DAYS} days."
    )


def no_vacation(view):
    """Route decorator (apply under @login_required): a nation on vacation
    can't use hostile/military actions."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        from database import get_request_cursor
        from helpers import error

        user_id = session.get("user_id")
        if user_id is not None:
            with get_request_cursor() as db:
                if is_on_vacation(db, user_id):
                    return error(403, ON_VACATION_ATTACKER_MSG)
        return view(*args, **kwargs)

    return wrapped
