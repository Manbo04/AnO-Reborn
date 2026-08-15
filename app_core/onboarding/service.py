"""Server-side onboarding progress for day-1 players."""
from __future__ import annotations

from database import get_request_cursor


def _province_count(db, user_id: int) -> int:
    db.execute("SELECT COUNT(*)::int FROM provinces WHERE userId = %s", (user_id,))
    row = db.fetchone()
    return int(row[0]) if row else 0


def _first_province_id(db, user_id: int) -> int | None:
    db.execute("SELECT id FROM provinces WHERE userId = %s ORDER BY id LIMIT 1", (user_id,))
    row = db.fetchone()
    return row[0] if row else None


def _food_bank_count(db, user_id: int) -> int:
    db.execute(
        """
        SELECT COALESCE(SUM(ub.quantity), 0)::int
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id = %s AND bd.name = 'food_banks'
        """,
        (user_id,),
    )
    row = db.fetchone()
    return int(row[0]) if row else 0


def _joined_coalition(db, user_id: int) -> bool:
    db.execute("SELECT coalition_id FROM users WHERE id = %s", (user_id,))
    row = db.fetchone()
    return (row[0] is not None) if row else False


def _active_treaties_count(db, user_id: int) -> int:
    db.execute(
        """
        SELECT COUNT(*)::int FROM nation_treaties
        WHERE status = 'active' AND (sender_id = %s OR recipient_id = %s)
        """,
        (user_id, user_id),
    )
    row = db.fetchone()
    return int(row[0]) if row else 0


def _tutorial_claimed_count(db, user_id: int) -> int:
    try:
        db.execute(
            "SELECT tutorial_chapters_claimed FROM stats WHERE id = %s",
            (user_id,),
        )
        row = db.fetchone()
        claimed = row[0] if row else None
        return len(list(claimed or []))
    except Exception:
        db.connection.rollback()
        return 0


def get_onboarding_status(db, user_id: int) -> dict:
    from database import query_cache
    cache_key = f"onboarding_status_{user_id}"
    cached = query_cache.get(cache_key)
    if cached is not None:
        return cached

    provinces = _province_count(db, user_id)
    food_banks = _food_bank_count(db, user_id)

    # Check coalition membership
    db.execute("SELECT coalition_id FROM users WHERE id = %s", (user_id,))
    row = db.fetchone()
    in_coalition = row[0] is not None if row else False

    # Check allies (active treaties)
    db.execute(
        """
        SELECT COUNT(*)::int FROM nation_treaties
        WHERE status = 'active' AND (sender_id = %s OR recipient_id = %s)
        """,
        (user_id, user_id),
    )
    row = db.fetchone()
    allies = row[0] if row else 0
    has_ally = allies >= 1

    steps = [
        {
            "id": "food_bank",
            "label": "Build a Food Bank",
            "done": food_banks >= 1,
            "href": "/provinces",
        },
        {
            "id": "coalition",
            "label": "Join a Coalition",
            "done": in_coalition,
            "href": "/coalitions",
        },
        {
            "id": "ally",
            "label": "Recruit an Ally",
            "done": has_ally,
            "href": "/treaties",
        },
    ]
    done_count = sum(1 for s in steps if s["done"])
    show_checklist = provinces >= 1 and (done_count < len(steps))

    result = {
        "steps": steps,
        "completed": done_count,
        "total": len(steps),
        "show_checklist": show_checklist,
        "tutorial_done": True,
        "show_tutorial_prompt": False,
        "tutorial_href": "/tutorial?onboard=1",
        "next_href": next((s["href"] for s in steps if not s["done"]), "/country"),
    }

    # If show_checklist is False, cache for longer since they won't see checklist again
    ttl = 600 if result["show_checklist"] is False else 30
    query_cache.set(cache_key, result, ttl_seconds=ttl)
    return result


def post_signup_redirect(user_id: int, *, has_recovery_key: bool = False) -> str:
    """Where to send a brand-new account after signup."""
    if has_recovery_key:
        return "/save_recovery_key"
    with get_request_cursor() as db:
        provinces = _province_count(db, user_id)
        if provinces == 0:
            return "/createprovince"
        status = get_onboarding_status(db, user_id)
    if status["show_checklist"]:
        return status["next_href"]
    return "/country"
