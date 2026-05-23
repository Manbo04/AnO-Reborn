#!/usr/bin/env python3
"""Apply migration 0022 (Discord bot tables + discord_id unique index).

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_discord_bot_migration.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "migrations" / "0022_discord_bot.sql"


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
                SELECT to_regclass('public.discord_link_codes') AS link_codes,
                       to_regclass('public.discord_guild_settings') AS guild_settings,
                       EXISTS (
                           SELECT 1 FROM pg_indexes
                           WHERE schemaname = 'public'
                             AND indexname = 'idx_users_discord_id_unique'
                       ) AS discord_id_unique
                """
            )
            row = cur.fetchone()
            print(
                f"  discord_link_codes={row[0]}, "
                f"discord_guild_settings={row[1]}, "
                f"discord_id_unique={row[2]}"
            )
        print("Done.")
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
