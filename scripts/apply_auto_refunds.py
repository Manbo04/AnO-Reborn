"""Apply conservative refunds based on recent negative_gold_reset repairs.

Usage:
  PYTHONPATH=. python scripts/apply_auto_refunds.py --dry-run
  PYTHONPATH=. python scripts/apply_auto_refunds.py --apply

Rules:
- Consider `repairs` rows with `change_type='negative_gold_reset'` in the last N days
- Refund amount = abs(before_gold) capped at MAX_REFUND
- Skip if a `refund_for_failed_trade` repair already exists for the user in the window
- When applying, do within a DB transaction:
  - update stats.gold += refund_amount
  - insert a `refund_for_failed_trade` repair row (details include original repair id)
- Log and print all actions
"""

import argparse
from datetime import datetime, timedelta, timezone
from database import get_db_connection, invalidate_user_cache
import json

CUTOFF_DAYS = 7
MAX_REFUND = 10000


def gather_candidates(cutoff_days=CUTOFF_DAYS, max_refund=MAX_REFUND):
    cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
    candidates = []
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            (
                "SELECT id, user_id, details, created_at FROM repairs "
                "WHERE change_type=%s AND created_at >= %s",
            ),
            ("negative_gold_reset", cutoff),
        )
        rows = db.fetchall()
        for rid, uid, details, created_at in rows:
            try:
                d = details if isinstance(details, dict) else json.loads(details)
                before = d.get("before_gold")
            except Exception:
                before = None
            if before is None:
                continue
            if before >= 0:
                continue
            amount = int(abs(before))
            if amount > max_refund:
                continue
            # skip if already refunded in window
            db.execute(
                "SELECT COUNT(*) FROM repairs WHERE user_id=%s "
                "AND change_type=%s AND created_at >= %s",
                (uid, "refund_for_failed_trade", cutoff),
            )
            if db.fetchone()[0] > 0:
                continue
            candidates.append(
                {
                    "repair_id": rid,
                    "user_id": uid,
                    "before_gold": before,
                    "refund_amount": amount,
                    "repair_created_at": created_at.isoformat(),
                }
            )
    return candidates


def apply_refunds(candidates):
    applied = []
    with get_db_connection() as conn:
        db = conn.cursor()
        for c in candidates:
            uid = c["user_id"]
            amt = c["refund_amount"]
            # Double check current data
            db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
            row = db.fetchone()
            if not row:
                continue
            before_gold = row[0] if row[0] is not None else 0
            db.execute(
                "UPDATE stats SET gold = gold + %s WHERE id=%s RETURNING gold",
                (amt, uid),
            )
            new_gold_row = db.fetchone()
            if not new_gold_row:
                continue
            details = {
                "refund_amount": amt,
                "based_on_repair_id": c["repair_id"],
                "note": "auto refund for possible failed trade",
            }
            db.execute(
                "INSERT INTO repairs (user_id, change_type, details) VALUES (%s,%s,%s)",
                (uid, "refund_for_failed_trade", json.dumps(details)),
            )
            try:
                invalidate_user_cache(uid)
            except Exception:
                pass
            applied.append(
                {
                    "user_id": uid,
                    "refund_amount": amt,
                    "before_gold": before_gold,
                    "after_gold": new_gold_row[0],
                }
            )
    return applied


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run", action="store_true", help="Show candidates, do not apply"
    )
    parser.add_argument("--apply", action="store_true", help="Apply refunds")
    args = parser.parse_args()

    candidates = gather_candidates()
    print("Candidates count:", len(candidates))
    for c in candidates:
        print(c)

    if args.apply:
        if not candidates:
            print("No candidates to apply")
        else:
            applied = apply_refunds(candidates)
            print("Applied refunds:")
            for a in applied:
                print(a)
