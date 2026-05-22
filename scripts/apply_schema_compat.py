#!/usr/bin/env python3
"""Apply schema compatibility migration 0021 (coalitions + discord_id).

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_schema_compat.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0021_coalition_members_and_discord_compat.sql"


def main() -> None:
    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: Set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)

    if not MIGRATION.exists():
        print(f"ERROR: Missing {MIGRATION}")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            sql = MIGRATION.read_text()
            print(f"Applying {MIGRATION.name}...")
            cur.execute(sql)
            cur.execute(
                """
                SELECT to_regclass('public.coalitions_legacy') AS legacy,
                       to_regclass('public.coalitions') AS flat,
                       EXISTS (
                           SELECT 1 FROM information_schema.columns
                           WHERE table_schema='public' AND table_name='users'
                             AND column_name='discord_id'
                       ) AS discord_id
                """
            )
            row = cur.fetchone()
            print(f"  coalitions_legacy={row[0]}, coalitions={row[1]}, discord_id={row[2]}")
        print("Done.")
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
