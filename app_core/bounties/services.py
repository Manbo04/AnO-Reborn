from app_core.market.repositories import (
    get_user_gold_for_update,
    decrement_gold,
    increment_gold,
    get_username,
    user_exists,
)
from app_core.world_affairs.services import log_event

from .repositories import (
    insert_bounty,
    get_bounty_for_update,
    set_bounty_cancelled,
    get_open_bounties_for_target,
    mark_bounties_claimed,
    get_all_open_bounties,
    count_open_bounties,
)

MIN_BOUNTY_AMOUNT = 1000
PAGE_SIZE = 30


def place_bounty(db, poster_id, target_id, amount):
    """Returns (ok, error_message_or_none, category)."""
    if target_id == poster_id:
        return False, "You cannot place a bounty on yourself.", "danger"

    if not user_exists(db, target_id):
        return False, "That nation does not exist.", "danger"

    if amount < MIN_BOUNTY_AMOUNT:
        return False, f"Bounties must be at least ${MIN_BOUNTY_AMOUNT:,}.", "danger"

    user_gold = get_user_gold_for_update(db, poster_id)
    if user_gold is None:
        return False, "Your nation data could not be found.", "danger"
    if amount > user_gold:
        return False, "You don't have enough gold for that bounty.", "danger"

    if not decrement_gold(db, poster_id, amount):
        return False, "You don't have enough gold for that bounty.", "danger"

    insert_bounty(db, target_id, poster_id, amount)

    poster_name = get_username(db, poster_id) or "A nation"
    target_name = get_username(db, target_id) or "a nation"
    log_event(
        db, "bounty_placed",
        f"{poster_name} placed a ${amount:,} bounty on {target_name}.",
        actor_id=poster_id, target_id=target_id,
    )
    return True, None, None


def cancel_bounty(db, bounty_id, poster_id):
    """Returns (ok, error_message_or_none, category)."""
    row = get_bounty_for_update(db, bounty_id)
    if not row or str(row[2]) != str(poster_id) or row[4] != "open":
        return False, "That bounty can't be cancelled.", "danger"

    amount = row[3]
    if not set_bounty_cancelled(db, bounty_id, poster_id):
        return False, "That bounty can't be cancelled.", "danger"

    increment_gold(db, poster_id, amount)
    return True, None, None


def claim_bounties(db, target_id, winner_id):
    """Called from war_orchestrator's independent connection the moment a war
    concludes. Pays every open bounty on target_id to winner_id. Returns the
    total paid out (0 if none)."""
    rows = get_open_bounties_for_target(db, target_id)
    if not rows:
        return 0

    total = 0
    bounty_ids = []
    for bounty_id, amount, poster_id in rows:
        total += amount
        bounty_ids.append(bounty_id)

    increment_gold(db, winner_id, total)
    mark_bounties_claimed(db, bounty_ids, winner_id)

    winner_name = get_username(db, winner_id) or "A nation"
    target_name = get_username(db, target_id) or "a nation"
    log_event(
        db, "bounty_claimed",
        f"{winner_name} collected ${total:,} in bounties for defeating {target_name}!",
        actor_id=winner_id, target_id=target_id,
    )
    return total


def fetch_bounty_board(db, page):
    page = max(1, page)
    total = count_open_bounties(db)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * PAGE_SIZE
    rows = get_all_open_bounties(db, PAGE_SIZE, offset)
    return rows, page, total_pages
