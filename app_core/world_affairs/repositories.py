def insert_event(db, event_type, message, actor_id=None, target_id=None):
    db.execute(
        "INSERT INTO world_events (event_type, message, actor_id, target_id) "
        "VALUES (%s, %s, %s, %s)",
        (event_type, message, actor_id, target_id),
    )


def get_events_page(db, limit, offset):
    db.execute(
        """
        SELECT we.id, we.event_type, we.message, we.actor_id, we.target_id, we.created_at,
               ua.username AS actor_name, ut.username AS target_name
        FROM world_events we
        LEFT JOIN users ua ON ua.id = we.actor_id
        LEFT JOIN users ut ON ut.id = we.target_id
        ORDER BY we.id DESC
        LIMIT %s OFFSET %s
        """,
        (limit, offset),
    )
    return db.fetchall()


def count_events(db):
    db.execute("SELECT COUNT(*) FROM world_events")
    row = db.fetchone()
    return row[0] if row else 0


def get_recent_messages(db, limit):
    """For the news ticker (province.py get_global_events) - plain strings only."""
    db.execute("SELECT message FROM world_events ORDER BY id DESC LIMIT %s", (limit,))
    return [row[0] for row in db.fetchall()]
