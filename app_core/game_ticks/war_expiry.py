"""Automatic war expiry tick and pure helpers.

Wars end automatically after 7 days if no peace has been agreed.
Ending has the same effect as a white peace: sets peace_date/status='ended'
with no reparations and no winner, and notifies both sides via news.
"""
from __future__ import annotations

import time

TASK_NAME = "war_auto_expiry"
ADVISORY_LOCK_ID = 9032
WAR_EXPIRY_DAYS = 7


def war_expired(started_at: float | None, now: float | None, days: int = WAR_EXPIRY_DAYS) -> bool:
    """Return True if the war started at least `days` days before `now`.

    Pure function for calculating war expiry.
    """
    if started_at is None or now is None:
        return False
    return (float(now) - float(started_at)) >= (float(days) * 86400.0)


def format_war_auto_end(
    started_at: float | None, now: float | None = None, days: int = WAR_EXPIRY_DAYS
) -> str:
    """Format remaining time before a war automatically ends.

    Returns: 'Ends automatically in Xd Yh'
    """
    if started_at is None:
        return "Ends automatically in 0d 0h"
    if now is None:
        now = time.time()
    remaining = (float(started_at) + float(days) * 86400.0) - float(now)
    if remaining <= 0:
        return "Ends automatically in 0d 0h"
    days_left = int(remaining // 86400)
    hours_left = int((remaining % 86400) // 3600)
    return f"Ends automatically in {days_left}d {hours_left}h"


def run_war_auto_expiry(db=None):
    """Periodic tick to end wars older than 7 days without a peace_date.

    Idempotent UPDATE ... RETURNING ensures double runs or concurrent executions
    are harmless and process each expired war exactly once.
    """
    def _execute(cursor):
        now_ts = time.time()
        cutoff_ts = now_ts - (WAR_EXPIRY_DAYS * 86400.0)

        # Idempotently end wars started > 7 days ago that have no peace_date
        cursor.execute(
            """
            UPDATE wars
            SET peace_date = %s, status = 'ended', peace_offer_id = NULL
            WHERE peace_date IS NULL AND start_date <= %s
            RETURNING id, attacker, defender
            """,
            (now_ts, cutoff_ts),
        )
        ended_wars = cursor.fetchall()
        if not ended_wars:
            return 0

        # Collect user ids to fetch usernames in batch
        user_ids = set()
        for _, att_id, def_id in ended_wars:
            user_ids.add(att_id)
            user_ids.add(def_id)

        cursor.execute(
            "SELECT id, username FROM users WHERE id = ANY(%s)",
            (list(user_ids),),
        )
        usernames = {row[0]: row[1] for row in cursor.fetchall()}

        news_rows = []
        for war_id, att_id, def_id in ended_wars:
            att_name = usernames.get(att_id, "Unknown")
            def_name = usernames.get(def_id, "Unknown")
            att_msg = f"Your war with {def_name} ended automatically after 7 days."
            def_msg = f"Your war with {att_name} ended automatically after 7 days."
            news_rows.append((att_id, att_msg))
            news_rows.append((def_id, def_msg))

        if news_rows:
            from psycopg2.extras import execute_batch

            execute_batch(
                cursor,
                "INSERT INTO news (destination_id, message) VALUES (%s, %s)",
                news_rows,
            )

        return len(ended_wars)

    if db is not None:
        return _execute(db)

    from database import get_db_connection

    with get_db_connection() as conn:
        cur = conn.cursor()
        count = _execute(cur)
        conn.commit()
        return count
