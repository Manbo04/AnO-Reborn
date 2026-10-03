#!/usr/bin/env python3
"""
Reimburse all players for 24 hours of missing revenue and replenish rations.

Bug context:
task_cursors.tax_income caused tax_income to run only every 2 hours instead
of every 1 hour, cutting tax revenue in half and draining player treasuries,
which subsequently caused food production (farms) to stall from lack of money.

This script:
1. Calculates 24h tax revenue per nation:
   max(24 * hourly_base_tax, 2 * last_24h_recorded_tax, last_24h_recorded_tax).
2. Atomically deposits 24h revenue into stats.gold for every nation.
3. Records the compensation in nation_revenue_history so players see it in their ledger.
4. Replenishes food (rations) in user_economy to at least a 24-hour supply so no nation starves.
5. Resets task_cursors.tax_income to 0.
6. Idempotently tracks completion in player_reimbursements table.
"""

import os
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REIMBURSEMENT_KEY = "tax_revenue_24h_2026_10_03"
MISSED_HOURS = 24
RATIONS_PER = 100  # population per ration from variables.py


def run_reimbursement():
    import psycopg2
    from psycopg2.extras import RealDictCursor

    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        # Fall back to database.py get_db_connection
        try:
            from database import get_db_connection
            with get_db_connection() as conn:
                _process_with_conn(conn)
                return
        except Exception as e:
            print(f"[reimburse] Could not establish DB connection via database.py: {e}")
            sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        conn.autocommit = False
        _process_with_conn(conn)
    finally:
        conn.close()


def _process_with_conn(conn):
    from psycopg2.extras import RealDictCursor

    cur = conn.cursor(cursor_factory=RealDictCursor)

    # 1. Ensure idempotency table exists
    cur.execute("""
        CREATE TABLE IF NOT EXISTS player_reimbursements (
            reimbursement_id TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            total_gold_distributed BIGINT,
            users_reimbursed INT,
            details JSONB
        )
    """)

    cur.execute(
        "SELECT applied_at FROM player_reimbursements WHERE reimbursement_id = %s",
        (REIMBURSEMENT_KEY,),
    )
    already_done = cur.fetchone()
    if already_done:
        print(f"[reimburse] Already applied on {already_done['applied_at']}. Skipping.")
        return

    # 2. Reset task_cursors.tax_income to 0 immediately
    cur.execute("CREATE TABLE IF NOT EXISTS task_cursors (task_name TEXT PRIMARY KEY, last_id BIGINT)")
    cur.execute(
        "INSERT INTO task_cursors (task_name, last_id) VALUES ('tax_income', 0) "
        "ON CONFLICT (task_name) DO UPDATE SET last_id = 0"
    )

    # 3. Calculate hourly base tax per user from provinces
    cur.execute("""
        SELECT p.userId as user_id,
               SUM(FLOOR(0.50 * p.population * (1 + LEAST(1.0, (p.land - 1) * 0.02)))) as hourly_income,
               SUM(p.population) as total_pop
        FROM provinces p
        JOIN users u ON u.id = p.userId
        GROUP BY p.userId
    """)
    province_data = {row["user_id"]: row for row in cur.fetchall()}

    # 4. Check tax revenue recorded in nation_revenue_history in last 24h
    cur.execute("""
        SELECT user_id, COALESCE(SUM(amount), 0) as last_24h_tax
        FROM nation_revenue_history
        WHERE category = 'tax' AND recorded_at >= NOW() - INTERVAL '24 hours'
        GROUP BY user_id
    """)
    history_taxes = {row["user_id"]: int(row["last_24h_tax"]) for row in cur.fetchall()}

    # 5. Get all users who have an active nation
    cur.execute("SELECT id FROM users ORDER BY id ASC")
    all_user_rows = cur.fetchall()

    # 6. Get rations resource_id
    cur.execute("SELECT resource_id FROM resource_dictionary WHERE name = 'rations'")
    rations_res_row = cur.fetchone()
    rations_resource_id = rations_res_row["resource_id"] if rations_res_row else None

    # Load current rations
    user_current_rations = {}
    if rations_resource_id:
        cur.execute(
            "SELECT user_id, quantity FROM user_economy WHERE resource_id = %s",
            (rations_resource_id,),
        )
        for r in cur.fetchall():
            user_current_rations[r["user_id"]] = r["quantity"] or 0

    reimbursement_records = []
    total_gold_distributed = 0
    rations_replenished_count = 0

    for u in all_user_rows:
        uid = u["id"]
        prov_info = province_data.get(uid)
        hourly_base = int(prov_info["hourly_income"]) if prov_info and prov_info["hourly_income"] else 0
        total_pop = int(prov_info["total_pop"]) if prov_info and prov_info["total_pop"] else 0
        hist_tax = history_taxes.get(uid, 0)

        # 24 hours of revenue compensation:
        # Base hourly * 24, or double what they received in the last 24h (since ticks were half),
        # whichever is higher.
        gold_compensation = max(hourly_base * MISSED_HOURS, hist_tax * 2, hist_tax)
        if gold_compensation <= 0 and total_pop > 0:
            gold_compensation = total_pop * MISSED_HOURS

        if gold_compensation > 0:
            # Credit to stats.gold
            cur.execute(
                "UPDATE stats SET gold = gold + %s WHERE id = %s",
                (gold_compensation, uid),
            )
            # Record in revenue ledger
            cur.execute(
                """
                INSERT INTO nation_revenue_history (user_id, category, amount)
                VALUES (%s, 'tax', %s)
                """,
                (uid, gold_compensation),
            )
            total_gold_distributed += gold_compensation
            reimbursement_records.append({"user_id": uid, "gold": gold_compensation})

        # Replenish food/rations if depleted or less than 24h supply
        if rations_resource_id and total_pop > 0:
            needed_hourly_rations = max(total_pop // RATIONS_PER, 1)
            needed_24h_rations = needed_hourly_rations * MISSED_HOURS
            cur_rations = user_current_rations.get(uid, 0)

            if cur_rations < needed_24h_rations:
                deficit = needed_24h_rations - cur_rations
                cur.execute(
                    """
                    INSERT INTO user_economy (user_id, resource_id, quantity)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, resource_id)
                    DO UPDATE SET quantity = user_economy.quantity + EXCLUDED.quantity
                    """,
                    (uid, rations_resource_id, deficit),
                )
                rations_replenished_count += 1

    # 7. Record marker
    cur.execute(
        """
        INSERT INTO player_reimbursements
            (reimbursement_id, total_gold_distributed, users_reimbursed, details)
        VALUES (%s, %s, %s, %s)
        """,
        (
            REIMBURSEMENT_KEY,
            total_gold_distributed,
            len(reimbursement_records),
            json.dumps({"rations_replenished_nations": rations_replenished_count}),
        ),
    )

    conn.commit()

    # 8. Best-effort cache invalidation
    try:
        from database import invalidate_user_cache
        for rec in reimbursement_records:
            try:
                invalidate_user_cache(rec["user_id"])
            except Exception:
                pass
    except Exception:
        pass

    print(f"[reimburse] Successfully reimbursed {len(reimbursement_records)} players!")
    print(f"[reimburse] Total gold distributed: {total_gold_distributed:,}")
    print(f"[reimburse] Nations with rations replenished: {rations_replenished_count}")


if __name__ == "__main__":
    run_reimbursement()
