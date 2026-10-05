"""
Replay the hourly province-revenue ticks lost on 2026-10-03.

Commit 6d8f82bd (live 09:22 UTC) made generate_province_revenue() select
provinces.location, a column that does not exist, so every production tick
from 09:25 through 20:25 UTC failed (12 ticks) until b027fdab went live at
20:37 UTC. Players got taxes but no resource production, upkeep or input use.

This re-runs the real tick 12 times so every nation gets exactly what those
ticks would have produced (and consumed). Idempotent: each replayed tick is
claimed in player_reimbursements BEFORE it runs, so a crash/restart can only
under-pay one tick, never pay twice. Runs from the worker boot in background.
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

MISSED_TICKS = 12
KEY_PREFIX = "production_replay_2026_10_03_tick_"
SCRIPT_LOCK = 7703100  # session advisory lock: one replayer at a time
TICK_LOCK_RETRIES = 20


def _last_run(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT last_run FROM task_runs WHERE task_name = 'generate_province_revenue'"
    )
    row = cur.fetchone()
    conn.commit()
    return row[0] if row else None


def main():
    from database import get_db_connection
    from app_core.game_ticks.revenue import generate_province_revenue

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (SCRIPT_LOCK,))
        if not cur.fetchone()[0]:
            print("[replay] another replayer holds the lock; exiting")
            return
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS player_reimbursements (
                reimbursement_id TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                total_gold_distributed BIGINT,
                users_reimbursed INT,
                details JSONB
            )
            """
        )
        conn.commit()

        replayed_any = False
        for i in range(1, MISSED_TICKS + 1):
            key = f"{KEY_PREFIX}{i:02d}"
            # Claim first: ON CONFLICT means already claimed/done -> skip.
            cur.execute(
                "INSERT INTO player_reimbursements (reimbursement_id, details) "
                "VALUES (%s, '{\"status\": \"claimed\"}'::jsonb) "
                "ON CONFLICT DO NOTHING RETURNING reimbursement_id",
                (key,),
            )
            claimed = cur.fetchone()
            conn.commit()
            if not claimed:
                print(f"[replay] {key} already done; skipping")
                continue
            replayed_any = True

            # Stay clear of the scheduled tick (:25) so we never make it skip.
            while 22 <= time.gmtime().tm_min <= 29:
                time.sleep(20)

            ok = False
            for attempt in range(TICK_LOCK_RETRIES):
                # Clear the min-interval guard so the tick is allowed to run now.
                cur.execute(
                    "UPDATE task_runs SET last_run = NULL "
                    "WHERE task_name = 'generate_province_revenue'"
                )
                cur.execute(
                    "UPDATE task_cursors SET last_id = 0 "
                    "WHERE task_name = 'generate_province_revenue'"
                )
                conn.commit()
                t0 = time.time()
                generate_province_revenue()
                # A real run sets last_run = now(); NULL means it was skipped
                # (scheduled tick held the lock) -> wait and retry.
                if _last_run(conn) is not None:
                    ok = True
                    print(f"[replay] {key} done in {time.time() - t0:.1f}s")
                    break
                print(f"[replay] {key} skipped (tick lock busy), retry {attempt + 1}")
                time.sleep(30)

            status = "done" if ok else "failed"
            cur.execute(
                "UPDATE player_reimbursements SET details = jsonb_build_object('status', %s::text), "
                "applied_at = NOW() WHERE reimbursement_id = %s",
                (status, key),
            )
            conn.commit()
            if not ok:
                print(f"[replay] {key} FAILED after retries; stopping")
                break

        # Don't let our last replay's last_run make the next scheduled tick skip.
        # Only when we actually replayed: clearing it on a no-op run made the
        # boot nudge see the tick as never-run and bill an extra upkeep tick
        # on every celery-worker deploy.
        if replayed_any:
            cur.execute(
                "UPDATE task_runs SET last_run = NULL "
                "WHERE task_name = 'generate_province_revenue'"
            )
        cur.execute("SELECT pg_advisory_unlock(%s)", (SCRIPT_LOCK,))
        conn.commit()
    print("[replay] finished")


if __name__ == "__main__":
    main()
