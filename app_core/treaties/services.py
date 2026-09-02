from .repositories import (
    get_active_treaties,
    get_incoming_treaties,
    get_outgoing_treaties,
    find_user_id_by_username,
    find_conflicting_treaty,
    insert_treaty_offer,
)

VALID_TREATY_TYPES = ["non_aggression", "mutual_defense"]


def list_treaties(db, user_id):
    """Returns (active, incoming, outgoing). On any query failure, rolls back
    and returns empty lists rather than raising - matches the original
    view_treaties()'s defensive try/except."""
    try:
        active = get_active_treaties(db, user_id)
        incoming = get_incoming_treaties(db, user_id)
        outgoing = get_outgoing_treaties(db, user_id)
        return active, incoming, outgoing
    except Exception:
        from database import rollback_db_cursor

        rollback_db_cursor(db)
        return [], [], []


def offer_treaty(db, sender_id, recipient_name, treaty_type):
    """Returns (ok, error_message_or_none, flash_category)."""
    if treaty_type not in VALID_TREATY_TYPES:
        return False, "Invalid treaty type.", "danger"

    recipient_id = find_user_id_by_username(db, recipient_name)
    if not recipient_id:
        return False, "Nation not found.", "danger"

    if sender_id == recipient_id:
        return False, "You cannot offer a treaty to yourself.", "danger"

    if find_conflicting_treaty(db, treaty_type, sender_id, recipient_id):
        return False, "A treaty of this type is already pending or active with this nation.", "warning"

    insert_treaty_offer(db, sender_id, recipient_id, treaty_type)
    return True, None, None
