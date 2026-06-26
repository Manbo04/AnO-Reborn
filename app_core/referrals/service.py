"""Referral code resolution, activity tracking, and reward payouts."""
from __future__ import annotations

import logging
import secrets
import string
from datetime import date, timezone
from typing import Any

from flask import request, session

from app_core.market.services import give_resource
from app_core.referrals.rewards import (
    INVITEE_SIGNUP_BONUS,
    MILESTONE_DAY_THRESHOLDS,
    MILESTONE_REWARDS,
    merge_rewards,
    reward_summary_text,
)

logger = logging.getLogger(__name__)

_schema_ready = False
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_REFERRAL_SITE = "https://affairsandorder.com"


def _normalize_code(code: str | None) -> str | None:
    if not code:
        return None
    cleaned = "".join(ch for ch in str(code).strip().upper() if ch.isalnum())
    if len(cleaned) < 4 or len(cleaned) > 12:
        return None
    return cleaned


def ensure_referral_schema(db) -> None:
    pass


def _generate_code() -> str:
    suffix = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(5))
    return f"ANO{suffix}"


def ensure_referral_code(db, user_id: int) -> str:
    ensure_referral_schema(db)
    db.execute(
        "SELECT referral_code FROM users WHERE id = %s",
        (user_id,),
    )
    row = db.fetchone()
    if row and row[0]:
        return row[0]

    for _ in range(12):
        candidate = _generate_code()
        db.execute(
            "SELECT id FROM users WHERE referral_code = %s",
            (candidate,),
        )
        if db.fetchone():
            continue
        db.execute(
            "UPDATE users SET referral_code = %s WHERE id = %s",
            (candidate, user_id),
        )
        return candidate

    raise RuntimeError(f"Could not allocate referral code for user_id={user_id}")


def referral_link_for_code(code: str) -> str:
    return f"{_REFERRAL_SITE}/signup?ref={code}"


def capture_referral_from_request() -> str | None:
    """Store ?ref= in session; return normalized code if present."""
    raw = request.args.get("ref")
    code = _normalize_code(raw)
    if code:
        session["referral_code"] = code
    return code


def referral_code_from_signup_request() -> str | None:
    code = _normalize_code(request.form.get("referral_code"))
    if code:
        return code
    return _normalize_code(session.get("referral_code"))


def resolve_referrer_id(db, code: str | None) -> int | None:
    normalized = _normalize_code(code)
    if not normalized:
        return None
    ensure_referral_schema(db)
    db.execute(
        "SELECT id FROM users WHERE referral_code = %s",
        (normalized,),
    )
    row = db.fetchone()
    return int(row[0]) if row else None


def _apply_rewards(db, user_id: int, rewards: dict[str, int]) -> dict[str, int]:
    granted: dict[str, int] = {}
    for resource, amount in rewards.items():
        if amount <= 0:
            continue
        if resource == "money":
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (amount, user_id),
            )
            granted["money"] = amount
            continue
        result = give_resource("bank", user_id, resource, amount, cursor=db)
        if result is not True:
            raise RuntimeError(f"Could not grant {amount} {resource}: {result}")
        granted[resource] = amount
    return granted


def link_referrer_on_signup(db, new_user_id: int, referral_code: str | None = None) -> int | None:
    """Attach referred_by_user_id if code is valid and not self-referral."""
    ensure_referral_schema(db)
    referrer_id = resolve_referrer_id(db, referral_code)
    if not referrer_id or referrer_id == new_user_id:
        return None
    db.execute(
        "UPDATE users SET referred_by_user_id = %s "
        "WHERE id = %s AND referred_by_user_id IS NULL",
        (referrer_id, new_user_id),
    )
    return referrer_id


def apply_signup_referral_bonus(db, user_id: int) -> dict[str, int] | None:
    ensure_referral_schema(db)
    db.execute(
        "SELECT referred_by_user_id FROM users WHERE id = %s",
        (user_id,),
    )
    row = db.fetchone()
    if not row or not row[0]:
        return None
    try:
        return _apply_rewards(db, user_id, INVITEE_SIGNUP_BONUS)
    except Exception:
        logger.exception("Failed signup referral bonus for user_id=%s", user_id)
        return None


def _user_is_verified(db, user_id: int) -> bool:
    db.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'users' AND column_name = 'is_verified'
        """
    )
    if not db.fetchone():
        return True
    db.execute(
        "SELECT COALESCE(is_verified, TRUE) FROM users WHERE id = %s",
        (user_id,),
    )
    row = db.fetchone()
    return bool(row[0]) if row else False


def record_active_day(db, user_id: int) -> int:
    """Record one UTC calendar day of activity; return total distinct days."""
    ensure_referral_schema(db)
    today = date.today()
    db.execute(
        """
        INSERT INTO referral_active_days (referred_user_id, activity_date)
        VALUES (%s, %s)
        ON CONFLICT DO NOTHING
        """,
        (user_id, today),
    )
    db.execute(
        "SELECT COUNT(*) FROM referral_active_days WHERE referred_user_id = %s",
        (user_id,),
    )
    row = db.fetchone()
    return int(row[0]) if row else 0


def _paid_milestones(db, referrer_id: int, referred_id: int) -> set[int]:
    db.execute(
        """
        SELECT milestone_days FROM referral_milestone_payouts
        WHERE referrer_user_id = %s AND referred_user_id = %s
        """,
        (referrer_id, referred_id),
    )
    return {int(r[0]) for r in db.fetchall()}


def try_grant_milestones(db, referred_user_id: int) -> list[dict[str, Any]]:
    """Pay inviter for any newly unlocked day milestones."""
    ensure_referral_schema(db)
    db.execute(
        "SELECT referred_by_user_id FROM users WHERE id = %s",
        (referred_user_id,),
    )
    row = db.fetchone()
    if not row or not row[0]:
        return []
    referrer_id = int(row[0])
    if not _user_is_verified(db, referred_user_id):
        return []

    active_days = record_active_day(db, referred_user_id)
    already_paid = _paid_milestones(db, referrer_id, referred_user_id)
    payouts: list[dict[str, Any]] = []

    for milestone_days in MILESTONE_DAY_THRESHOLDS:
        if active_days < milestone_days or milestone_days in already_paid:
            continue
        rewards = MILESTONE_REWARDS.get(milestone_days, {})
        if not rewards:
            continue
        db.execute(
            """
            INSERT INTO referral_milestone_payouts
              (referrer_user_id, referred_user_id, milestone_days)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (referrer_id, referred_user_id, milestone_days),
        )
        granted = _apply_rewards(db, referrer_id, rewards)
        payouts.append(
            {
                "milestone_days": milestone_days,
                "referrer_id": referrer_id,
                "referred_user_id": referred_user_id,
                "granted": granted,
            }
        )
        logger.info(
            "Referral milestone %sd: referrer=%s referred=%s granted=%s",
            milestone_days,
            referrer_id,
            referred_user_id,
            granted,
        )
    return payouts


def process_referral_activity(db, user_id: int) -> None:
    """Called from hourly activity ping — track day and pay milestones."""
    try:
        ensure_referral_schema(db)
        record_active_day(db, user_id)
        try_grant_milestones(db, user_id)
    except Exception:
        logger.exception("Referral activity processing failed for user_id=%s", user_id)


def get_referral_dashboard(db, user_id: int) -> dict[str, Any]:
    ensure_referral_schema(db)
    code = ensure_referral_code(db, user_id)
    db.execute(
        """
        SELECT u.id, u.username,
               (SELECT COUNT(*)::int FROM referral_active_days rad
                WHERE rad.referred_user_id = u.id) AS days_active
        FROM users u
        WHERE u.referred_by_user_id = %s
        ORDER BY u.id DESC
        """,
        (user_id,),
    )
    invitees = []
    for row in db.fetchall():
        referred_id = int(row[0])
        paid = _paid_milestones(db, user_id, referred_id)
        earned = merge_rewards(
            *(MILESTONE_REWARDS.get(d, {}) for d in paid)
        )
        next_milestone = next(
            (d for d in MILESTONE_DAY_THRESHOLDS if d not in paid),
            None,
        )
        invitees.append(
            {
                "user_id": referred_id,
                "username": row[1],
                "days_active": int(row[2] or 0),
                "is_verified": _user_is_verified(db, referred_id),
                "milestones_paid": sorted(paid),
                "next_milestone": next_milestone,
                "earned_summary": reward_summary_text(earned) if earned else "—",
            }
        )

    milestone_goals = []
    for days in MILESTONE_DAY_THRESHOLDS:
        rewards = MILESTONE_REWARDS[days]
        milestone_goals.append(
            {
                "days": days,
                "summary": reward_summary_text(rewards),
            }
        )

    return {
        "referral_code": code,
        "referral_link": referral_link_for_code(code),
        "invitee_bonus_summary": reward_summary_text(INVITEE_SIGNUP_BONUS),
        "invitees": invitees,
        "milestone_goals": milestone_goals,
        "total_invitees": len(invitees),
    }
