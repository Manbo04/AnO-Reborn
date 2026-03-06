#!/usr/bin/env python3
"""
Compensate all players for the generate_province_revenue outage.

Outage window: 2026-03-03 19:25 UTC to 2026-03-05 23:25 UTC (~52 hours)
Cause: stale session-level advisory lock (PID 35094) blocked the task.

Compensation: 52 hours × per-user hourly tax income (base rate, no CG bonus)
Formula per province: floor(0.50 * population * (1 + min(1.0, (land-1)*0.02)))
Sum across all provinces for each user, multiply by 52.

This script:
1. Calculates compensation per user
2. Logs gold_before and gold_after for audit
3. Updates stats.gold atomically
"""

import os
import sys
import csv
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MISSED_HOURS = 52
TAX_RATE = 0.50
LAND_MULTIPLIER = 0.02
LAND_CAP = 1.0


def main():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_PUBLIC_URL or DATABASE_URL must be set")
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Calculate compensation per user
    cur.execute("""
        SELECT p.userId as user_id,
               SUM(FLOOR(0.50 * p.population
                   * (1 + LEAST(1.0, (p.land - 1) * 0.02)))) as hourly_income
        FROM provinces p
        JOIN users u ON u.id = p.userId
        GROUP BY p.userId
    """)
    user_incomes = {row["user_id"]: int(row["hourly_income"]) for row in cur.fetchall()}

    if not user_incomes:
        print("No users with provinces found. Exiting.")
        conn.close()
        return

    # Snapshot current gold
    user_ids = list(user_incomes.keys())
    cur.execute("SELECT id, gold FROM stats WHERE id = ANY(%s)", (user_ids,))
    gold_before = {row["id"]: int(row["gold"]) for row in cur.fetchall()}

    # Build audit log
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    audit_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "backups",
        f"revenue_compensation_{timestamp}.csv",
    )

    audit_rows = []
    for uid, hourly in sorted(user_incomes.items()):
        compensation = hourly * MISSED_HOURS
        before = gold_before.get(uid, 0)
        after = before + compensation
        audit_rows.append({
            "user_id": uid,
            "gold_before": before,
            "hourly_income": hourly,
            "hours": MISSED_HOURS,
            "compensation": compensation,
            "gold_after": after,
        })

    # Write audit CSV
    os.makedirs(os.path.dirname(audit_file), exist_ok=True)
    with open(audit_file, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "user_id", "gold_before", "hourly_income",
                "hours", "compensation", "gold_after",
            ],
        )
        writer.writeheader()
        writer.writerows(audit_rows)
    print(f"Audit log written to: {audit_file}")

    # Apply compensation
    update_count = 0
    for row in audit_rows:
        cur.execute(
            "UPDATE stats SET gold = gold + %s WHERE id = %s",
            (row["compensation"], row["user_id"]),
        )
        update_count += cur.rowcount

    conn.commit()
    total_comp = sum(r["compensation"] for r in audit_rows)
    print(f"Compensation applied to {update_count} users.")
    print(f"Total gold distributed: {total_comp:,}")
    print(f"Hours compensated: {MISSED_HOURS}")
    print(f"Min: {min(r['compensation'] for r in audit_rows):,}")
    print(f"Max: {max(r['compensation'] for r in audit_rows):,}")

    conn.close()


if __name__ == "__main__":
    main()
