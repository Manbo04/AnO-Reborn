"""Server-side onboarding progress for day-1 players."""
from __future__ import annotations

from database import get_request_cursor


def _province_count(db, user_id: int) -> int:
    db.execute("SELECT COUNT(*)::int FROM provinces WHERE owner_id = %s", (user_id,))
    row = db.fetchone()
    return int(row[0]) if row else 0


def _farm_count(db, user_id: int) -> int:
    db.execute(
        """
        SELECT COALESCE(SUM(ub.quantity), 0)::int
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id = %s AND bd.name = 'farms'
        """,
        (user_id,),
    )
    row = db.fetchone()
    return int(row[0]) if row else 0


def _tutorial_claimed_count(db, user_id: int) -> int:
    db.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'stats' AND column_name = 'tutorial_chapters_claimed'
        """
    )
    if not db.fetchone():
        return 0
    db.execute(
        "SELECT tutorial_chapters_claimed FROM stats WHERE id = %s",
        (user_id,),
    )
    row = db.fetchone()
    claimed = row[0] if row else None
    return len(list(claimed or []))


def get_onboarding_status(db, user_id: int) -> dict:
    provinces = _province_count(db, user_id)
    farms = _farm_count(db, user_id)
    chapters = _tutorial_claimed_count(db, user_id)

    steps = [
        {
            "id": "tutorial",
            "label": "Read tutorial chapter 1",
            "done": chapters >= 1,
            "href": "/tutorial?onboard=1",
        },
        {
            "id": "province",
            "label": "Create your first province",
            "done": provinces >= 1,
            "href": "/createprovince",
        },
        {
            "id": "farm",
            "label": "Build a farm",
            "done": farms >= 1,
            "href": "/provinces" if provinces else "/createprovince",
        },
    ]
    done_count = sum(1 for s in steps if s["done"])
    tutorial_done = chapters >= 1
    return {
        "steps": steps,
        "completed": done_count,
        "total": len(steps),
        "show_checklist": done_count < len(steps),
        "tutorial_done": tutorial_done,
        "show_tutorial_prompt": not tutorial_done,
        "tutorial_href": "/tutorial?onboard=1",
        "next_href": next((s["href"] for s in steps if not s["done"]), "/country"),
    }


def post_signup_redirect(user_id: int, *, has_recovery_key: bool = False) -> str:
    """Where to send a brand-new account after signup."""
    if has_recovery_key:
        return "/save_recovery_key"
    with get_request_cursor() as db:
        status = get_onboarding_status(db, user_id)
    if status["show_checklist"]:
        return status["next_href"]
    return "/country"
