#!/usr/bin/env python3
"""
Read-only production/DB health check for progression smoothness.

Checks task_runs freshness and province-chunk lag for large nations.

Usage:
  DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHUNK_SIZE = int(os.getenv("PROVINCE_REVENUE_CHUNK_SIZE", "200"))
STALE_MINUTES = 90


def main() -> int:
    if not (os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")):
        print("SKIP: no DATABASE_PUBLIC_URL / DATABASE_URL")
        return 0

    from database import get_db_connection

    now = datetime.now(timezone.utc)
    issues = []

    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            """
            SELECT task_name, last_run, status
            FROM task_runs
            ORDER BY last_run DESC NULLS LAST
            LIMIT 20
            """
        )
        rows = db.fetchall()
        print("task_runs (recent):")
        for name, last_run, status in rows:
            age_m = None
            if last_run:
                lr = last_run.replace(tzinfo=timezone.utc) if last_run.tzinfo is None else last_run
                age_m = (now - lr).total_seconds() / 60
            print(f"  {name:30} {status or '-':8} last_run={last_run} age_min={age_m:.0f}" if age_m else f"  {name:30} {status or '-':8} last_run={last_run}")
            if age_m and age_m > STALE_MINUTES and name in (
                "generate_province_revenue",
                "tax_income",
                "population_growth",
            ):
                issues.append(f"P0: {name} stale {age_m:.0f}m")

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
        print("\nTop nations by province count (revenue cycle hours = ceil(n/200)):")
        for uid, n in top:
            hours = (n + CHUNK_SIZE - 1) // CHUNK_SIZE
            flag = " P2: >24h cycle" if hours > 24 else ""
            print(f"  user {uid}: {n} provinces -> ~{hours}h per full revenue pass{flag}")
            if hours > 24:
                issues.append(f"P2: user {uid} needs ~{hours}h for full revenue chunk cycle")

    if issues:
        print("\nISSUES:")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("\nOK: no stale critical tasks or extreme chunk lag in top 10")
    return 0


if __name__ == "__main__":
    sys.exit(main())
