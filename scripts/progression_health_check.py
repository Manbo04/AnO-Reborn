#!/usr/bin/env python3
"""
Read-only production/DB health check for progression smoothness.

Checks task_runs freshness, game_tick_logs, economy updated_at, and chunk lag.

Usage:
  DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
"""


import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHUNK_SIZE = int(os.getenv("PROVINCE_REVENUE_CHUNK_SIZE", "200"))
STALE_MINUTES = 90
CRITICAL_TASKS = (
    "generate_province_revenue",
    "tax_income",
    "population_growth",
    "global_tick",
    "execute_trade_agreements",
)


def _age_minutes(now: datetime, ts) -> float | None:
    if not ts:
        return None
    lr = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
    return (now - lr).total_seconds() / 60


def main() -> int:
    if not (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")):
        print("SKIP: no DATABASE_PUBLIC_URL / DATABASE_URL")
        return 0

    from database import get_db_connection

    now = datetime.now(timezone.utc)
    issues: list[str] = []

    with get_db_connection() as conn:
        db = conn.cursor()

        db.execute(
            """
            SELECT task_name, last_run
            FROM task_runs
            ORDER BY last_run DESC NULLS LAST
            LIMIT 20
            """
        )
        rows = db.fetchall()
        print("task_runs (recent):")
        for name, last_run in rows:
            age_m = _age_minutes(now, last_run)
            line = f"  {name:30} last_run={last_run}"
            if age_m is not None:
                line += f" age_min={age_m:.0f}"
            print(line)
            if age_m and age_m > STALE_MINUTES and name in CRITICAL_TASKS:
                issues.append(f"P0: task_runs.{name} stale {age_m:.0f}m")

        db.execute(
            """
            SELECT 1 FROM information_schema.tables
            WHERE table_name = 'game_tick_logs'
            """
        )
        if db.fetchone():
            db.execute(
                """
                SELECT tick_type, status, started_at
                FROM game_tick_logs
                ORDER BY tick_id DESC
                LIMIT 5
                """
            )
            print("\ngame_tick_logs (recent):")
            for tick_type, status, started_at in db.fetchall():
                age_m = _age_minutes(now, started_at)
                print(
                    f"  {tick_type:25} {status:10} started={started_at} "
                    f"age_min={age_m:.0f}" if age_m else f"  {tick_type} {status} {started_at}"
                )
            db.execute("SELECT MAX(started_at) FROM game_tick_logs")
            last_tick = db.fetchone()[0]
            tick_age = _age_minutes(now, last_tick)
            if tick_age and tick_age > STALE_MINUTES:
                issues.append(f"P0: game_tick_logs last tick stale {tick_age:.0f}m")

        db.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'user_economy' AND column_name = 'updated_at'
            """
        )
        if db.fetchone():
            db.execute("SELECT MAX(updated_at) FROM user_economy")
            last_econ = db.fetchone()[0]
            econ_age = _age_minutes(now, last_econ)
            print(f"\nuser_economy max updated_at: {last_econ} (age_min={econ_age:.0f})")
            if econ_age and econ_age > STALE_MINUTES:
                issues.append(f"P0: no user_economy updates for {econ_age:.0f}m")

        db.execute(
            """
            SELECT userid, COUNT(*) AS n
            FROM provinces
            GROUP BY userid
            ORDER BY n DESC
            LIMIT 10
            """
        )
        top = db.fetchall()
        print("\nTop nations by province count (hours per full revenue pass = ceil(n/200)):")
        for uid, n in top:
            hours = (n + CHUNK_SIZE - 1) // CHUNK_SIZE
            flag = " P2: >24h cycle" if hours > 24 else ""
            print(f"  user {uid}: {n} provinces -> ~{hours}h{flag}")
            if hours > 24:
                issues.append(f"P2: user {uid} needs ~{hours}h for full revenue chunk cycle")

    if issues:
        print("\nISSUES:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("\nOK: tasks and economy updates look fresh; no extreme chunk lag in top 10")
    return 0


if __name__ == "__main__":
    sys.exit(main())
