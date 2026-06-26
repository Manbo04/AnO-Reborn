"""Tutorial reward claim API."""
from flask import Blueprint, jsonify, request, session

from app_core.market.services import give_resource
from app_core.tutorial.rewards import (
    CHAPTER_REWARDS,
    GRADUATION_REWARD,
    merge_rewards,
)
from database import get_request_cursor
from helpers import login_required

bp = Blueprint("tutorial_api", __name__)

_columns_ready = False


def _ensure_tutorial_columns(db) -> None:
    global _columns_ready
    if _columns_ready:
        return
    db.execute(
        "ALTER TABLE stats ADD COLUMN IF NOT EXISTS "
        "tutorial_chapters_claimed INTEGER[] DEFAULT '{}'"
    )
    db.execute(
        "ALTER TABLE stats ADD COLUMN IF NOT EXISTS "
        "tutorial_graduated_at TIMESTAMPTZ"
    )
    _columns_ready = True


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


@bp.route("/api/tutorial/progress", methods=["GET"])
@login_required
def tutorial_progress():
    user_id = session["user_id"]
    with get_request_cursor() as db:
        _ensure_tutorial_columns(db)
        db.execute(
            """
            SELECT tutorial_chapters_claimed, tutorial_graduated_at
            FROM stats WHERE id = %s
            """,
            (user_id,),
        )
        row = db.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Nation not found"}), 404
    claimed = sorted(int(x) for x in (row[0] or []))
    return jsonify(
        {
            "ok": True,
            "chapters_claimed": claimed,
            "graduated": row[1] is not None,
        }
    )


@bp.route("/api/tutorial/claim", methods=["POST"])
@login_required
def claim_tutorial_reward():
    user_id = session["user_id"]
    payload = request.get_json(silent=True) or {}
    chapter_index = payload.get("chapter_index")
    graduate = bool(payload.get("graduate"))

    if chapter_index is None and not graduate:
        return jsonify({"ok": False, "error": "chapter_index or graduate required"}), 400

    with get_request_cursor() as db:
        _ensure_tutorial_columns(db)
        db.execute(
            """
            SELECT tutorial_chapters_claimed, tutorial_graduated_at
            FROM stats WHERE id = %s
            """,
            (user_id,),
        )
        row = db.fetchone()
        if not row:
            return jsonify({"ok": False, "error": "Nation not found"}), 404

        claimed = list(row[0] or [])
        graduated_at = row[1]
        rewards_to_grant: dict[str, int] = {}
        messages = []

        if chapter_index is not None:
            try:
                idx = int(chapter_index)
            except (TypeError, ValueError):
                return jsonify({"ok": False, "error": "Invalid chapter_index"}), 400
            if idx < 0 or idx > 9:
                return jsonify({"ok": False, "error": "chapter_index out of range"}), 400
            if idx in claimed:
                return jsonify(
                    {
                        "ok": True,
                        "already_claimed": True,
                        "granted": {},
                        "message": "Chapter reward already claimed.",
                    }
                )
            chapter_reward = CHAPTER_REWARDS.get(idx, {})
            if chapter_reward:
                rewards_to_grant = merge_rewards(rewards_to_grant, chapter_reward)
                messages.append(f"Chapter {idx + 1} reward")
            claimed.append(idx)
            db.execute(
                "UPDATE stats SET tutorial_chapters_claimed = %s WHERE id = %s",
                (claimed, user_id),
            )

        if graduate:
            if graduated_at:
                return jsonify(
                    {
                        "ok": True,
                        "already_claimed": True,
                        "granted": {},
                        "message": "Graduation bonus already claimed.",
                    }
                )
            rewards_to_grant = merge_rewards(rewards_to_grant, GRADUATION_REWARD)
            messages.append("Graduation bonus")
            db.execute(
                "UPDATE stats SET tutorial_graduated_at = now() WHERE id = %s",
                (user_id,),
            )

        if not rewards_to_grant:
            return jsonify(
                {
                    "ok": True,
                    "granted": {},
                    "message": "Nothing to grant for this milestone.",
                }
            )

        try:
            granted = _apply_rewards(db, user_id, rewards_to_grant)
        except RuntimeError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 500

    try:
        from database import invalidate_user_cache

        invalidate_user_cache(user_id)
    except Exception:
        pass

    return jsonify(
        {
            "ok": True,
            "granted": granted,
            "message": " · ".join(messages) + " applied to your nation.",
        }
    )


def advance_tutorial_step_by_action(db, user_id: int, action: str) -> None:
    # Map the string action to the corresponding chapter index
    ACTION_CHAPTER_MAP = {
        "build_farm": 0,
        "build_distribution_center": 1,
        "build_mine": 2, 
    }
    
    target_chapter = ACTION_CHAPTER_MAP.get(action)
    if target_chapter is None:
        return
        
    _ensure_tutorial_columns(db)
    
    # Try adding tutorial_step if it doesn't exist
    try:
        db.execute("ALTER TABLE stats ADD COLUMN IF NOT EXISTS tutorial_step INTEGER DEFAULT 0")
    except Exception:
        pass

    db.execute(
        "SELECT tutorial_chapters_claimed FROM stats WHERE id = %s",
        (user_id,)
    )
    row = db.fetchone()
    if not row:
        return
        
    claimed = list(row[0] or [])
        
    # Prevent claiming twice
    if target_chapter in claimed:
        return
        
    # Apply rewards automatically
    from app_core.tutorial.rewards import CHAPTER_REWARDS
    chapter_reward = CHAPTER_REWARDS.get(target_chapter, {})
    
    if chapter_reward:
        from app_core.tutorial.routes import _apply_rewards
        _apply_rewards(db, user_id, chapter_reward)
        
    claimed.append(target_chapter)
    db.execute(
        "UPDATE stats SET tutorial_chapters_claimed = %s, tutorial_step = %s WHERE id = %s",
        (claimed, target_chapter + 1, user_id)
    )
    
    # Invalidate user cache to ensure UI updates
    try:
        from database import invalidate_user_cache
        invalidate_user_cache(user_id)
    except Exception:
        pass

