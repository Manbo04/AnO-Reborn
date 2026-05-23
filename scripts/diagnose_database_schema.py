#!/usr/bin/env python3
"""Detect whether Postgres is AnO-Reborn (legacy) or incompatible (e.g. Next.js overhaul).

Usage:
  DATABASE_PUBLIC_URL='postgresql://...' python3 scripts/diagnose_database_schema.py

Exit codes:
  0 — legacy AnO schema detected (safe for bot + migrations)
  1 — wrong / unknown schema
"""

from __future__ import annotations

import os
import sys

import psycopg2
from dotenv import load_dotenv

load_dotenv()

LEGACY_MARKERS = (
    "users",
    "stats",
    "provinces",
    "wars",
    "user_economy",
    "resource_dictionary",
)

NEXTJS_MARKERS = (
    "User",
    "Nation",
    "Province",
    "Account",
)


def main() -> int:
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: set DATABASE_PUBLIC_URL or DATABASE_URL")
        return 1

    conn = psycopg2.connect(url)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name
            """
        )
        tables = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    print(f"Public tables: {len(tables)}")
    legacy_hits = [t for t in LEGACY_MARKERS if t in tables]
    next_hits = [t for t in NEXTJS_MARKERS if t in tables]

    print("\n=== AnO-Reborn (legacy Flask) markers ===")
    for t in LEGACY_MARKERS:
        mark = "OK" if t in tables else "MISSING"
        print(f"  [{mark}] {t}")

    print("\n=== Next.js overhaul markers (incompatible with this repo) ===")
    for t in NEXTJS_MARKERS:
        mark = "FOUND" if t in tables else "—"
        print(f"  [{mark}] {t}")

    if legacy_hits and not next_hits:
        print("\n✅ LEGACY AnO schema — bot, web, and migrations 0022/0023 are compatible.")
        if "discord_guild_settings" not in tables:
            print("   Run: python3 scripts/apply_discord_bot_migration.py")
            print("        python3 scripts/apply_discord_guild_panels_migration.py")
        return 0

    if next_hits and not legacy_hits:
        print(
            "\n❌ NEXT.JS (or non-legacy) schema — WRONG DATABASE VOLUME for AnO-Reborn."
        )
        print("   Do NOT run init_db_railway.py (wipes data).")
        print("   Railway → Postgres → Volumes → attach the volume that has table 'users'.")
        print("   The live Affairs & Order game uses lowercase users/stats/provinces.")
        return 1

    if legacy_hits and next_hits:
        print("\n⚠️  Mixed schema — investigate manually before migrations.")
        return 1

    print("\n❌ Empty or unknown schema — wrong volume or fresh database.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
