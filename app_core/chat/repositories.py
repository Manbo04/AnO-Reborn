"""DB access for coalition group chat and 1:1 nation direct messages.

Uses ``get_db_cursor`` (commits/rolls back within its own ``with`` block)
rather than ``get_request_cursor`` (request-scoped, committed by
``teardown_request`` at the end of a normal Flask request) everywhere here,
even in code paths also reachable from plain HTTP routes. Flask-SocketIO
event handlers only get an app context, not a full request context, so
``teardown_request`` never fires for them -- a write made via
``get_request_cursor`` inside a socket handler is silently never committed
(found via a live repro: the INSERT ran with no error, but neither an
independent connection in the same process nor a fresh psql session ever
saw it). ``get_db_cursor`` doesn't depend on that hook, so it's correct in
both contexts.
"""

from database import get_db_cursor, get_coalition_members_table

MAX_MESSAGE_LENGTH = 1000

# Shared "equipped name flair" join, inlined directly into each chat query
# below (rather than a separate batch lookup) to avoid an N+1 per page load
# -- see app_core/store/repositories.py::get_equipped_flair for the
# single/batch-call-site equivalent used by the Country page.
_FLAIR_JOIN_SQL = """
    LEFT JOIN stats st ON st.id = u.id
    LEFT JOIN cosmetics nc ON nc.id = st.equipped_name_color_cosmetic_id AND nc.is_active = TRUE
    LEFT JOIN cosmetics bd ON bd.id = st.equipped_badge_cosmetic_id      AND bd.is_active = TRUE
    LEFT JOIN cosmetics tt ON tt.id = st.equipped_title_cosmetic_id      AND tt.is_active = TRUE
"""
_FLAIR_SELECT_SQL = "nc.value, bd.value, bd.name, tt.name"


def _flair_dict(name_color, badge_icon, badge_name, title):
    return {"name_color": name_color, "badge_icon": badge_icon, "badge_name": badge_name, "title": title}


def is_coalition_member(user_id, coalition_id):
    members_tbl = get_coalition_members_table()
    if not members_tbl:
        return False
    with get_db_cursor(read_only=True) as db:
        db.execute(
            f"SELECT 1 FROM {members_tbl} WHERE userid=%s AND colid=%s",
            (user_id, coalition_id),
        )
        return db.fetchone() is not None


def create_coalition_message(coalition_id, sender_id, content):
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO coalition_messages (coalition_id, sender_id, content)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (coalition_id, sender_id, content),
        )
        row = db.fetchone()
        db.execute(
            f"SELECT u.username, {_FLAIR_SELECT_SQL} FROM users u {_FLAIR_JOIN_SQL} WHERE u.id=%s",
            (sender_id,),
        )
        sender_row = db.fetchone()
    return {
        "id": row[0],
        "coalition_id": coalition_id,
        "sender_id": sender_id,
        "sender_username": sender_row[0] if sender_row else "Unknown",
        "content": content,
        "created_at": row[1].isoformat(),
        "flair": _flair_dict(*sender_row[1:]) if sender_row else _flair_dict(None, None, None, None),
    }


def list_coalition_messages(coalition_id, limit=50):
    with get_db_cursor(read_only=True) as db:
        db.execute(
            f"""
            SELECT cm.id, cm.sender_id, u.username, cm.content, cm.created_at,
                   {_FLAIR_SELECT_SQL}
            FROM coalition_messages cm
            JOIN users u ON u.id = cm.sender_id
            {_FLAIR_JOIN_SQL}
            WHERE cm.coalition_id = %s
            ORDER BY cm.id DESC
            LIMIT %s
            """,
            (coalition_id, limit),
        )
        rows = db.fetchall() or []
    return [
        {
            "id": r[0],
            "coalition_id": coalition_id,
            "sender_id": r[1],
            "sender_username": r[2],
            "content": r[3],
            "created_at": r[4].isoformat(),
            "flair": _flair_dict(*r[5:]),
        }
        for r in reversed(rows)
    ]


def create_global_chat_message(sender_id, content):
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO global_chat_messages (sender_id, content)
            VALUES (%s, %s)
            RETURNING id, created_at
            """,
            (sender_id, content),
        )
        row = db.fetchone()
        db.execute(
            f"SELECT u.username, {_FLAIR_SELECT_SQL} FROM users u {_FLAIR_JOIN_SQL} WHERE u.id=%s",
            (sender_id,),
        )
        sender_row = db.fetchone()
    return {
        "id": row[0],
        "sender_id": sender_id,
        "sender_username": sender_row[0] if sender_row else "Unknown",
        "content": content,
        "created_at": row[1].isoformat(),
        "flair": _flair_dict(*sender_row[1:]) if sender_row else _flair_dict(None, None, None, None),
    }


def list_global_chat_messages(limit=30):
    with get_db_cursor(read_only=True) as db:
        db.execute(
            f"""
            SELECT gcm.id, gcm.sender_id, u.username, gcm.content, gcm.created_at,
                   {_FLAIR_SELECT_SQL}
            FROM global_chat_messages gcm
            JOIN users u ON u.id = gcm.sender_id
            {_FLAIR_JOIN_SQL}
            ORDER BY gcm.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = db.fetchall() or []
    return [
        {
            "id": r[0],
            "sender_id": r[1],
            "sender_username": r[2],
            "content": r[3],
            "created_at": r[4].isoformat(),
            "flair": _flair_dict(*r[5:]),
        }
        for r in reversed(rows)
    ]


def create_direct_message(sender_id, recipient_id, content):
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO direct_messages (sender_id, recipient_id, content)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (sender_id, recipient_id, content),
        )
        row = db.fetchone()
        db.execute(
            f"SELECT u.username, {_FLAIR_SELECT_SQL} FROM users u {_FLAIR_JOIN_SQL} WHERE u.id=%s",
            (sender_id,),
        )
        sender_row = db.fetchone()
    return {
        "id": row[0],
        "sender_id": sender_id,
        "recipient_id": recipient_id,
        "sender_username": sender_row[0] if sender_row else "Unknown",
        "content": content,
        "created_at": row[1].isoformat(),
        "flair": _flair_dict(*sender_row[1:]) if sender_row else _flair_dict(None, None, None, None),
    }


def list_conversation_messages(user_a, user_b, limit=50):
    with get_db_cursor(read_only=True) as db:
        db.execute(
            f"""
            SELECT dm.id, dm.sender_id, dm.recipient_id, u.username, dm.content, dm.created_at,
                   {_FLAIR_SELECT_SQL}
            FROM direct_messages dm
            JOIN users u ON u.id = dm.sender_id
            {_FLAIR_JOIN_SQL}
            WHERE (dm.sender_id = %s AND dm.recipient_id = %s)
               OR (dm.sender_id = %s AND dm.recipient_id = %s)
            ORDER BY dm.id DESC
            LIMIT %s
            """,
            (user_a, user_b, user_b, user_a, limit),
        )
        rows = db.fetchall() or []
    return [
        {
            "id": r[0],
            "sender_id": r[1],
            "recipient_id": r[2],
            "sender_username": r[3],
            "content": r[4],
            "created_at": r[5].isoformat(),
            "flair": _flair_dict(*r[6:]),
        }
        for r in reversed(rows)
    ]


def mark_conversation_read(user_id, other_user_id):
    with get_db_cursor() as db:
        db.execute(
            """
            UPDATE direct_messages SET read_at = now()
            WHERE recipient_id = %s AND sender_id = %s AND read_at IS NULL
            """,
            (user_id, other_user_id),
        )


def list_conversations_for_user(user_id):
    """Most-recent-message-first list of this user's DM conversations."""
    with get_db_cursor(read_only=True) as db:
        db.execute(
            """
            SELECT other_id, u.username, last_content, last_created_at, unread_count
            FROM (
                SELECT
                    CASE WHEN sender_id = %s THEN recipient_id ELSE sender_id END AS other_id,
                    (ARRAY_AGG(content ORDER BY id DESC))[1] AS last_content,
                    MAX(created_at) AS last_created_at,
                    COUNT(*) FILTER (WHERE recipient_id = %s AND read_at IS NULL) AS unread_count
                FROM direct_messages
                WHERE sender_id = %s OR recipient_id = %s
                GROUP BY other_id
            ) conv
            JOIN users u ON u.id = conv.other_id
            ORDER BY last_created_at DESC
            """,
            (user_id, user_id, user_id, user_id),
        )
        rows = db.fetchall() or []
    return [
        {
            "other_user_id": r[0],
            "other_username": r[1],
            "last_message": r[2],
            "last_message_at": r[3].isoformat(),
            "unread_count": r[4],
        }
        for r in rows
    ]


def unread_dm_total(user_id):
    with get_db_cursor(read_only=True) as db:
        db.execute(
            "SELECT COUNT(*) FROM direct_messages WHERE recipient_id=%s AND read_at IS NULL",
            (user_id,),
        )
        row = db.fetchone()
    return row[0] if row else 0
