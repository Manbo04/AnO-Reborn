"""Apply default refunds to accounts matching a safe heuristic.

Heuristic:
 - stats.gold < 1
 - user has 0 provinces
 - refund amount: DEFAULT_REFUND (100)
 - caps and skips are applied conservatively

This script logs every repair to the `repairs` table as `refund_for_failed_trade`.

Usage:
  PYTHONPATH=. python scripts/apply_default_refunds.py
"""

from database import get_db_connection, invalidate_user_cache
from datetime import datetime, timezone

DEFAULT_REFUND = 100
MAX_TOTAL_REFUND = 10000  # absolute cap for safety


def apply_default_refunds():
    applied = []
    now_dt = datetime.now(timezone.utc)
    now = now_dt.isoformat()
    with get_db_connection() as conn:
        db = conn.cursor()

        # Ensure repairs table exists
        db.execute(
            "CREATE TABLE IF NOT EXISTS repairs (id SERIAL PRIMARY KEY, "
            "user_id INT, change_type TEXT, details JSONB, "
            "created_at TIMESTAMP WITH TIME ZONE DEFAULT now())"
        )

        # Find candidate users: gold < 1 AND no provinces
        rows_query = (
            "SELECT s.id, s.gold FROM stats s LEFT JOIN ("
            "SELECT userId, COUNT(*) as cnt FROM provinces GROUP BY userId) p "
            "ON p.userId = s.id "
            "WHERE s.gold < %s AND COALESCE(p.cnt, 0) = 0"
        )
        db.execute(rows_query, (1,))
        rows = db.fetchall()

        for uid, gold in rows:
            try:
                refund = DEFAULT_REFUND
                if refund > MAX_TOTAL_REFUND:
                    refund = MAX_TOTAL_REFUND

                before = gold if gold is not None else 0

                # Apply refund
                db.execute(
                    "UPDATE stats SET gold = gold + %s WHERE id=%s RETURNING gold",
                    (refund, uid),
                )
                new_row = db.fetchone()
                if not new_row:
                    continue

                details = {
                    "before_gold": before,
                    "refund_amount": refund,
                    "note": "default auto-refund (low-gold/no-provinces)",
                    "applied_at": now,
                }

                import json

                insert_sql = (
                    "INSERT INTO repairs (user_id, change_type, details) "
                    "VALUES (%s,%s,%s)"
                )
                db.execute(
                    insert_sql, (uid, "refund_for_failed_trade", json.dumps(details))
                )

                try:
                    invalidate_user_cache(uid)
                except Exception:
                    pass

                applied.append(
                    {
                        "user_id": uid,
                        "before": before,
                        "after": new_row[0],
                        "refund": refund,
                    }
                )

            except Exception as exc:
                # Log and continue
                print("Failed to refund user", uid, exc)

    return applied


if __name__ == "__main__":
    candidates = apply_default_refunds()
    print("Applied refunds count:", len(candidates))
    for c in candidates:
        print(c)
