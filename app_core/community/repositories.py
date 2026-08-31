"""DB access for the homepage hub's Devlog (admin changelog) and Discussions
(public forum) sections.

Uses ``get_request_cursor`` throughout since every caller here is a plain
HTTP route (unlike app_core/chat/repositories.py, which also serves
Socket.IO handlers with no request context).
"""

from database import get_request_cursor

TITLE_MAX_LENGTH = 200
DEVLOG_BODY_MAX_LENGTH = 4000
THREAD_BODY_MAX_LENGTH = 4000
REPLY_MAX_LENGTH = 2000


def create_devlog_entry(author_id, title, body):
    with get_request_cursor() as db:
        db.execute(
            """
            INSERT INTO devlog_entries (author_id, title, body)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (author_id, title, body),
        )
        row = db.fetchone()
    return {"id": row[0], "created_at": row[1]}


def list_devlog_entries(limit=10):
    with get_request_cursor() as db:
        db.execute(
            """
            SELECT de.id, de.title, de.body, de.created_at, u.username
            FROM devlog_entries de
            JOIN users u ON u.id = de.author_id
            ORDER BY de.id DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = db.fetchall() or []
    return [
        {"id": r[0], "title": r[1], "body": r[2], "created_at": r[3], "author": r[4]}
        for r in rows
    ]


def create_thread(author_id, title, body):
    with get_request_cursor() as db:
        db.execute(
            """
            INSERT INTO forum_threads (author_id, title, body)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (author_id, title, body),
        )
        row = db.fetchone()
    return {"id": row[0], "created_at": row[1]}


def list_threads(limit=20):
    with get_request_cursor() as db:
        db.execute(
            """
            SELECT ft.id, ft.title, ft.created_at, ft.last_activity_at, u.username,
                   (SELECT COUNT(*) FROM forum_replies fr WHERE fr.thread_id = ft.id) AS reply_count
            FROM forum_threads ft
            JOIN users u ON u.id = ft.author_id
            ORDER BY ft.last_activity_at DESC
            LIMIT %s
            """,
            (limit,),
        )
        rows = db.fetchall() or []
    return [
        {
            "id": r[0],
            "title": r[1],
            "created_at": r[2],
            "last_activity_at": r[3],
            "author": r[4],
            "reply_count": r[5],
        }
        for r in rows
    ]


def get_thread(thread_id):
    with get_request_cursor() as db:
        db.execute(
            """
            SELECT ft.id, ft.title, ft.body, ft.created_at, u.username, ft.author_id
            FROM forum_threads ft
            JOIN users u ON u.id = ft.author_id
            WHERE ft.id = %s
            """,
            (thread_id,),
        )
        row = db.fetchone()
        if not row:
            return None
        db.execute(
            """
            SELECT fr.id, fr.content, fr.created_at, u.username, fr.author_id
            FROM forum_replies fr
            JOIN users u ON u.id = fr.author_id
            WHERE fr.thread_id = %s
            ORDER BY fr.id ASC
            """,
            (thread_id,),
        )
        reply_rows = db.fetchall() or []
    return {
        "id": row[0],
        "title": row[1],
        "body": row[2],
        "created_at": row[3],
        "author": row[4],
        "author_id": row[5],
        "replies": [
            {
                "id": r[0],
                "content": r[1],
                "created_at": r[2],
                "author": r[3],
                "author_id": r[4],
            }
            for r in reply_rows
        ],
    }


def create_reply(thread_id, author_id, content):
    with get_request_cursor() as db:
        db.execute(
            "SELECT id FROM forum_threads WHERE id=%s",
            (thread_id,),
        )
        if not db.fetchone():
            return None
        db.execute(
            """
            INSERT INTO forum_replies (thread_id, author_id, content)
            VALUES (%s, %s, %s)
            RETURNING id, created_at
            """,
            (thread_id, author_id, content),
        )
        row = db.fetchone()
        db.execute(
            "UPDATE forum_threads SET last_activity_at = now() WHERE id=%s",
            (thread_id,),
        )
    return {"id": row[0], "created_at": row[1]}


def delete_thread(thread_id, requester_id, is_admin):
    with get_request_cursor() as db:
        db.execute("SELECT author_id FROM forum_threads WHERE id=%s", (thread_id,))
        row = db.fetchone()
        if not row:
            return False
        if row[0] != requester_id and not is_admin:
            return False
        db.execute("DELETE FROM forum_threads WHERE id=%s", (thread_id,))
    return True


def delete_reply(reply_id, requester_id, is_admin):
    with get_request_cursor() as db:
        db.execute("SELECT author_id, thread_id FROM forum_replies WHERE id=%s", (reply_id,))
        row = db.fetchone()
        if not row:
            return False
        if row[0] != requester_id and not is_admin:
            return False
        db.execute("DELETE FROM forum_replies WHERE id=%s", (reply_id,))
    return True
