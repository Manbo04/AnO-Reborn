"""Generic unique-nation-trait registry.

A trait handler provides:
  daily_tick(db, user_id, now) -> dict | None   run once per dawn per holder
  page_context(db, user_id, viewer_id) -> dict | None   data for the nation page
  partial                                         template that renders it
Adding a trait = one config line (config.py) + one handler registered here.
"""
import logging
import os

from . import config, golden_throne

logger = logging.getLogger(__name__)

HANDLERS = {
    golden_throne.TRAIT_KEY: {
        "daily_tick": golden_throne.run_dawn,
        "page_context": golden_throne.page_context,
        "partial": "partials/traits/golden_throne.html",
    },
}


def disabled():
    return os.getenv("NATION_TRAITS_DISABLED") == "1"


def sync_assignments(db):
    """Make nation_traits match config (idempotent). Removed lines are disabled, not deleted."""
    wanted = set()
    for user_id, keys in config.TRAIT_ASSIGNMENTS.items():
        for key in keys:
            if key not in HANDLERS:
                continue
            wanted.add((user_id, key))
            db.execute(
                "INSERT INTO nation_traits (user_id, trait_key) "
                "SELECT %s, %s WHERE EXISTS (SELECT 1 FROM users WHERE id=%s) "
                "ON CONFLICT (user_id, trait_key) DO UPDATE SET enabled = TRUE",
                (user_id, key, user_id),
            )
            if key == golden_throne.TRAIT_KEY:
                golden_throne.ensure_state(db, user_id)
    db.execute("SELECT user_id, trait_key FROM nation_traits WHERE enabled")
    for user_id, key in db.fetchall():
        if (user_id, key) not in wanted:
            db.execute(
                "UPDATE nation_traits SET enabled = FALSE WHERE user_id=%s AND trait_key=%s",
                (user_id, key),
            )


def run_daily(db):
    """Tick hook: run every enabled trait's daily step. Each holder is isolated in a savepoint
    so one failure cannot break the others (or the tick)."""
    results = {}
    sync_assignments(db)
    db.execute("SELECT user_id, trait_key FROM nation_traits WHERE enabled")
    for user_id, key in db.fetchall():
        handler = HANDLERS.get(key)
        if not handler:
            continue
        db.execute("SAVEPOINT trait_daily")
        try:
            results[f"{user_id}:{key}"] = handler["daily_tick"](db, user_id)
            db.execute("RELEASE SAVEPOINT trait_daily")
        except Exception:
            logger.exception("trait daily tick failed for %s/%s", user_id, key)
            db.execute("ROLLBACK TO SAVEPOINT trait_daily")
    return results


def page_contexts(db, owner_id, viewer_id):
    """List of {key, partial, ctx} for the traits a nation page should render."""
    out = []
    db.execute(
        "SELECT trait_key FROM nation_traits WHERE user_id=%s AND enabled", (owner_id,)
    )
    for (key,) in db.fetchall():
        handler = HANDLERS.get(key)
        if not handler:
            continue
        ctx = handler["page_context"](db, owner_id, viewer_id)
        if ctx:
            out.append({"key": key, "partial": handler["partial"], "ctx": ctx})
    return out
