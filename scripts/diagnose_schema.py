#!/usr/bin/env python3
"""Report schema/migration alignment for production debugging.

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/diagnose_schema.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = sorted((ROOT / "migrations").glob("*.sql"))


def main() -> None:
    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: Set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    failed = False

    print("=== Core tables ===")
    for tbl in (
        "resource_dictionary",
        "user_economy",
        "building_dictionary",
        "user_buildings",
        "task_runs",
        "game_tick_logs",
    ):
        cur.execute("SELECT to_regclass(%s)", (f"public.{tbl}",))
        ok = cur.fetchone()[0] is not None
        print(f"  {'OK' if ok else 'MISSING':7} {tbl}")
        if not ok:
            failed = True

    print("\n=== Optional columns ===")
    checks = [
        ("users", "last_active"),
        ("users", "join_number"),
        ("users", "discord_id"),
        ("users", "flag_data"),
        ("provinces", "pop_children"),
        ("user_buildings", "province_id"),
        ("colnames", "tax_rate"),
        ("colnames", "flag_data"),
    ]
    for table, col in checks:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s AND column_name=%s
            """,
            (table, col),
        )
        ok = cur.fetchone() is not None
        print(f"  {'OK' if ok else 'MISSING':7} {table}.{col}")
        if col in (
            "last_active",
            "pop_children",
            "province_id",
            "resource_dictionary",
        ) and not ok:
            failed = True

    print("\n=== Coalition membership table ===")
    cur.execute(
        """
        SELECT CASE
            WHEN to_regclass('public.coalitions_legacy') IS NOT NULL
                THEN 'coalitions_legacy'
            WHEN to_regclass('public.coalitions') IS NOT NULL
                THEN 'coalitions'
            ELSE NULL
        END
        """
    )
    print(f"  {cur.fetchone()[0] or 'NONE'}")

    print("\n=== Hot-path indexes ===")
    index_checks = [
        "idx_user_tech_user_unlocked",
        "idx_news_destination_id",
        "idx_users_last_active",
    ]
    for idx in index_checks:
        cur.execute("SELECT to_regclass(%s)", (f"public.{idx}",))
        ok = cur.fetchone()[0] is not None
        print(f"  {'OK' if ok else 'MISSING':7} {idx}")

    print("\n=== Revenue task freshness ===")
    cur.execute(
        """
        SELECT last_run,
               EXTRACT(EPOCH FROM (now() - last_run)) AS age_seconds
        FROM task_runs
        WHERE task_name = 'generate_province_revenue'
        """
    )
    row = cur.fetchone()
    if row and row[0]:
        print(f"  last_run={row[0]} age_seconds={int(row[1] or 0)}")
        if (row[1] or 0) > 7200:
            print("  WARN: revenue task older than 2 hours")
            failed = True
    else:
        print("  MISSING task_runs row for generate_province_revenue")
        failed = True

    print(f"\n=== SQL migrations on disk ({len(MIGRATIONS)} files) ===")
    for path in MIGRATIONS[-5:]:
        print(f"  {path.name}")

    cur.close()
    conn.close()
    if failed:
        print("\nFAILED: schema gaps detected")
        sys.exit(1)
    print("\nOK: critical schema checks passed")


if __name__ == "__main__":
    main()
