"""Log repairs for refunds that were applied but not recorded due to earlier failure.

Heuristic: users with gold == DEFAULT_REFUND and no provinces and no existing
`refund_for_failed_trade` repair row will get a repair row inserted indicating a
retroactive logged refund.
"""

from database import get_db_connection

import json

DEFAULT_REFUND = 100


def log_missing_refunds():
    added = []
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "CREATE TABLE IF NOT EXISTS repairs (id SERIAL PRIMARY KEY, "
            "user_id INT, change_type TEXT, details JSONB, "
            "created_at TIMESTAMP WITH TIME ZONE DEFAULT now())"
        )

        rows_query = (
            "SELECT s.id, s.gold FROM stats s LEFT JOIN ("
            "SELECT userId, COUNT(*) as cnt FROM provinces GROUP BY userId) p "
            "ON p.userId=s.id "
            "WHERE s.gold = %s AND COALESCE(p.cnt,0)=0"
        )
        db.execute(rows_query, (DEFAULT_REFUND,))
        rows = db.fetchall()
        for uid, _ in rows:
            # skip if already has refund log
            db.execute(
                "SELECT COUNT(*) FROM repairs WHERE user_id=%s AND change_type=%s",
                (uid, "refund_for_failed_trade"),
            )
            if db.fetchone()[0] > 0:
                continue

            details = {
                "before_gold": 0,
                "refund_amount": DEFAULT_REFUND,
                "note": "retroactive refund log",
            }
            insert_sql = (
                "INSERT INTO repairs (user_id, change_type, details) "
                "VALUES (%s,%s,%s)"
            )
            db.execute(
                insert_sql, (uid, "refund_for_failed_trade", json.dumps(details))
            )
            added.append({"user_id": uid, "refund": DEFAULT_REFUND})
    return added


if __name__ == "__main__":
    added = log_missing_refunds()
    print("Logged refunds for count:", len(added))
    for a in added:
        print(a)
