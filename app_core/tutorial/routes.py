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

def _claim_chapter(db, user_id: int, idx: int) -> dict[str, int] | None:
    """Atomically mark chapter `idx` claimed for user_id. Returns the
    chapter's reward dict if this call actually won the claim, or None if
    it was already claimed (by this call or a concurrent one) -- the
    array-containment check and the write happen in one UPDATE, so this
    is safe under concurrent callers with no lock required. See
    claim_tutorial_reward()'s docstring for the race this closes."""
    db.execute(
        """
        UPDATE stats
        SET tutorial_chapters_claimed =
            COALESCE(tutorial_chapters_claimed, ARRAY[]::int[]) || ARRAY[%s]::int[]
        WHERE id = %s
          AND NOT (COALESCE(tutorial_chapters_claimed, ARRAY[]::int[]) @> ARRAY[%s]::int[])
        RETURNING tutorial_chapters_claimed
        """,
        (idx, user_id, idx),
    )
    if db.fetchone() is None:
        return None
    return CHAPTER_REWARDS.get(idx, {})


def _claim_graduation(db, user_id: int) -> bool:
    """Atomically mark graduation claimed for user_id. Returns True if
    this call actually won the claim, False if already graduated (by
    this call or a concurrent one)."""
    db.execute(
        """
        UPDATE stats SET tutorial_graduated_at = now()
        WHERE id = %s AND tutorial_graduated_at IS NULL
        RETURNING tutorial_graduated_at
        """,
        (user_id,),
    )
    return db.fetchone() is not None


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
        db.execute(
            """
            SELECT tutorial_chapters_claimed, tutorial_graduated_at, tutorial_step
            FROM stats WHERE id = %s
            """,
            (user_id,),
        )
        row = db.fetchone()
    if not row:
        return jsonify({"ok": False, "error": "Nation not found"}), 404
    claimed = sorted(int(x) for x in (row[0] or []))
    tutorial_step = row[2] if len(row) > 2 else 0
    return jsonify(
        {
            "ok": True,
            "chapters_claimed": claimed,
            "tutorial_step": tutorial_step,
            "graduated": bool(row[1]),
        }
    )


@bp.route("/api/tutorial/claim", methods=["POST"])
@login_required
def claim_tutorial_reward():
    """FIXED 2026-09-23: found live while auditing app_core/tutorial/
    during the account cross-contamination investigation (unrelated to
    that bug, found along the way) -- real double-grant race, same class
    as several other fixes this session. The old logic read
    tutorial_chapters_claimed/tutorial_graduated_at, checked membership
    in Python, then wrote back an unconditional UPDATE with no lock and
    no atomic guard -- two concurrent claims for the same chapter (or two
    concurrent graduation claims) both read "not yet claimed" before
    either commits, both pass the check, and both call _apply_rewards(),
    double-granting real gold/resources for a single milestone.
    Also called from advance_tutorial_step_by_action() below as a side
    effect of building purchases, which don't uniformly hold a per-user
    lock around this call (some purchase paths do, e.g. mass_purchase
    across several provinces in one request does not) -- rather than
    relying on every caller to remember a lock, both claim paths below
    now use an atomic conditional UPDATE (PostgreSQL's array containment
    operator for the chapter array, a plain NULL check for the
    already-a-single-value graduation timestamp) so the idempotency
    check IS the write, with RETURNING telling us whether this call
    actually won the race -- correct regardless of what the caller does.
    """
    user_id = session["user_id"]
    payload = request.get_json(silent=True) or {}
    chapter_index = payload.get("chapter_index")
    graduate = bool(payload.get("graduate"))

    if chapter_index is None and not graduate:
        return jsonify({"ok": False, "error": "chapter_index or graduate required"}), 400

    idx = None
    if chapter_index is not None:
        try:
            idx = int(chapter_index)
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": "Invalid chapter_index"}), 400
        if idx < 0 or idx > 9:
            return jsonify({"ok": False, "error": "chapter_index out of range"}), 400

    with get_request_cursor() as db:
        db.execute("SELECT 1 FROM stats WHERE id = %s", (user_id,))
        if not db.fetchone():
            return jsonify({"ok": False, "error": "Nation not found"}), 404

        rewards_to_grant: dict[str, int] = {}
        messages = []
        anything_already_claimed = False

        if idx is not None:
            claimed_reward = _claim_chapter(db, user_id, idx)
            if claimed_reward is None:
                anything_already_claimed = True
            elif claimed_reward:
                rewards_to_grant = merge_rewards(rewards_to_grant, claimed_reward)
                messages.append(f"Chapter {idx + 1} reward")

        if graduate:
            if _claim_graduation(db, user_id):
                rewards_to_grant = merge_rewards(rewards_to_grant, GRADUATION_REWARD)
                messages.append("Graduation bonus")
            else:
                anything_already_claimed = True

        if not rewards_to_grant:
            return jsonify(
                {
                    "ok": True,
                    "already_claimed": anything_already_claimed,
                    "granted": {},
                    "message": (
                        "Already claimed."
                        if anything_already_claimed
                        else "Nothing to grant for this milestone."
                    ),
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
    """FIXED 2026-09-23: see claim_tutorial_reward()'s docstring -- this
    had the exact same non-atomic read-check-write race on
    tutorial_chapters_claimed. Called as a side effect of building
    purchases (app_core/economy/building_purchase.py), and not every
    purchase path holds a per-user lock around that call (mass-purchase
    across several provinces in one request does not), so this can't rely
    on caller locking -- now uses the same atomic _claim_chapter() helper
    the direct claim API uses.
    """
    # Map the string action to the corresponding chapter index
    ACTION_CHAPTER_MAP = {
        "build_farm": 0,
        "build_distribution_center": 1,
        "build_mine": 2,
        "build_food_bank": 3,
    }

    target_chapter = ACTION_CHAPTER_MAP.get(action)
    if target_chapter is None:
        return

    chapter_reward = _claim_chapter(db, user_id, target_chapter)
    if chapter_reward is None:
        # Already claimed (by this call or a concurrent one) -- nothing to do.
        return

    if chapter_reward:
        _apply_rewards(db, user_id, chapter_reward)

    db.execute(
        "UPDATE stats SET tutorial_step = %s WHERE id = %s AND tutorial_step < %s",
        (target_chapter + 1, user_id, target_chapter + 1),
    )

    # Invalidate user cache to ensure UI updates
    try:
        from database import invalidate_user_cache
        invalidate_user_cache(user_id)
    except Exception:
        pass

