#!/usr/bin/env python3
"""Detect whether Postgres is AnO-Reborn (legacy) or incompatible (e.g. Next.js overhaul).

Usage:
  DATABASE_PUBLIC_URL='postgresql://...' python3 scripts/diagnose_database_schema.py

Exit codes:
  0 — legacy AnO schema OR Next.js bridged with compatibility views
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


def _relation_kinds(cur) -> dict[str, str]:
    cur.execute(
        """
        SELECT c.relname, c.relkind
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r', 'v', 'm')
        """
    )
    return {r[0]: r[1] for r in cur.fetchall()}


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
        kinds = _relation_kinds(cur)
    finally:
        conn.close()

    print(f"Public tables/views: {len(tables)}")
    legacy_hits = [t for t in LEGACY_MARKERS if t in tables]
    next_hits = [t for t in NEXTJS_MARKERS if t in tables]

    print("\n=== AnO-Reborn (legacy Flask) markers ===")
    for t in LEGACY_MARKERS:
        kind = kinds.get(t)
        if t in tables:
            suffix = " (view)" if kind == "v" else " (table)" if kind == "r" else ""
            print(f"  [OK] {t}{suffix}")
        else:
            print(f"  [MISSING] {t}")

    print("\n=== Next.js overhaul markers ===")
    for t in NEXTJS_MARKERS:
        mark = "FOUND" if t in tables else "—"
        print(f"  [{mark}] {t}")

    users_is_view = kinds.get("users") == "v"
    bridged = bool(legacy_hits and next_hits and users_is_view)

    if legacy_hits and not next_hits:
        print("\n✅ LEGACY AnO schema — bot, web, and migrations 0022/0023 are compatible.")
        if "discord_guild_settings" not in tables:
            print("   Run: python3 scripts/apply_discord_bot_migration.py")
            print("        python3 scripts/apply_discord_guild_panels_migration.py")
        return 0

    if bridged:
        print(
            "\n✅ BRIDGED schema — Prisma tables + legacy compatibility views."
        )
        print("   Python/bot should use User.id (via users view), not Nation.id.")
        print("   If views are missing/outdated:")
        print("        python3 scripts/apply_nextjs_compat_views.py")
        if "discord_guild_settings" not in tables:
            print("   Then: python3 scripts/apply_discord_bot_migration.py")
        return 0

    if next_hits and not legacy_hits:
        print(
            "\n❌ NEXT.JS schema without legacy views — run bridge script or attach legacy volume."
        )
        print("   Do NOT run init_db_railway.py (wipes data).")
        print("   python3 scripts/apply_nextjs_compat_views.py")
        print("   Legacy player data may be on volume postgres-active-data.")
        return 1

    if legacy_hits and next_hits:
        print(
            "\n⚠️  Mixed schema without users view — run apply_nextjs_compat_views.py or investigate."
        )
        return 1

    print("\n❌ Empty or unknown schema — wrong volume or fresh database.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
