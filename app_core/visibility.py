"""Who counts as a "genuine player", and who can be targeted.

Two independent per-nation flags on ``users``:

* ``hidden_from_rankings`` - the nation never appears on leaderboards, score
  tables or "top N" lists (the owner/test accounts). Bot nations
  (``auth_type = 'bot'``) are always hidden too, whether or not the flag is set,
  so a freshly spawned bot can never leak onto a leaderboard.
* ``untargetable`` - other nations can't interact with it (war, spying,
  trade/treaty offers, bounties, coalition invites, direct messages, embargoes).
  The nation itself can still act on everyone else. Bots are NOT untargetable.

Every read tolerates the columns not being migrated yet (treated as "not
hidden / targetable") so a deploy can't break the game ahead of the migration.
"""
from app_core.vacation import _optional_fetch

UNTARGETABLE_MSG = "That nation can't be targeted."


def ranked_sql(alias: str = "u") -> str:
    """SQL predicate selecting only genuine, publicly ranked players."""
    return (
        f"({alias}.auth_type IS DISTINCT FROM 'bot' "
        f"AND NOT COALESCE({alias}.hidden_from_rankings, FALSE))"
    )


def is_untargetable(db, user_id) -> bool:
    """Is this nation closed to interaction from other players?"""
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return False
    row = _optional_fetch(
        db,
        "SELECT COALESCE(untargetable, FALSE) FROM users WHERE id=%s",
        (user_id,),
    )
    return bool(row and row[0])


def blocks_interaction(db, actor_id, target_id) -> bool:
    """True when ``actor_id`` may not act on ``target_id`` (self is exempt)."""
    try:
        if int(actor_id) == int(target_id):
            return False
    except (TypeError, ValueError):
        return False
    return is_untargetable(db, target_id)
