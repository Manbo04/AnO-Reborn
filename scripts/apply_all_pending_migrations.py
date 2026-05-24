#!/usr/bin/env python3
"""Apply SQL migrations 0011-0023 idempotently (production maintenance).

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_all_pending_migrations.py
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_all_pending_migrations.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]

# Order matters for fresh DBs; files use IF NOT EXISTS where possible.
MIGRATION_FILES = [
    "0011_add_users_last_active.sql",
    "0012_add_join_number.sql",
    "0013_add_demographics_education_schema.sql",
    "0016_add_coalition_tax_rate.sql",
    "0017_add_performance_indexes.sql",
    "0015_add_hotpath_indexes.sql",
    "0018_cleanup_indexes_add_spyinfo.sql",
    "0021_coalition_members_and_discord_compat.sql",
    "0022_discord_bot.sql",
    "0023_discord_guild_panels.sql",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: Set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()

    for name in MIGRATION_FILES:
        path = ROOT / "migrations" / name
        if not path.exists():
            print(f"SKIP missing {name}")
            continue
        sql = path.read_text()
        print(f"{'[dry-run] ' if args.dry_run else ''}Applying {name}...")
        if not args.dry_run:
            try:
                cur.execute(sql)
            except Exception as exc:
                print(f"  WARN {name}: {exc}")

    if not args.dry_run:
        from database import ensure_schema_compat

        ensure_schema_compat()
        print("Ran ensure_schema_compat()")

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
