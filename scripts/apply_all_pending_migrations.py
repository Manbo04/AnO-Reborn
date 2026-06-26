#!/usr/bin/env python3
"""Apply SQL migrations idempotently (production maintenance).

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_all_pending_migrations.py
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_all_pending_migrations.py --dry-run
"""


import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Order matters; 0001-0010 assumed applied on long-lived prod DBs.
MIGRATION_FILES = [
    "0011_add_users_last_active.sql",
    "0012_add_join_number.sql",
    "0013_add_demographics_education_schema.sql",
    "0015_add_hotpath_indexes.sql",
    "0016_add_coalition_tax_rate.sql",
    "0017_add_performance_indexes.sql",
    "0018_cleanup_indexes_add_spyinfo.sql",
    "0019_fix_maintenance_costs.sql",
    "0020_enforce_population_demographics_sync.sql",
    "0021_coalition_members_and_discord_compat.sql",
    "0022_discord_bot.sql",
    "0023_discord_guild_panels.sql",
    "0024_nextjs_compat_views.sql",
    "0025_tech_tree_prerequisites.sql",
    "0026_fix_building_costs.sql",
    "0027_deprecate_distribution_centers.sql",
    "0028_add_world_map_nodes.sql",
    "0029_optimize_queries.sql",
    "0030_tutorial_rewards.sql",
    "0030_world_map_tiers.sql",
    "0031_advertisements.sql",
    "0032_poll_votes.sql",
    "0033_optimize_schema.sql",
    "0034_add_users_recovery_key.sql",
    "0035_add_provinces_image_data.sql",
    "0036_referrals.sql",
    "0030_add_furnace_projects.sql",
]


def _ensure_migration_table(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            name VARCHAR(128) PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _already_applied(cur, name: str) -> bool:
    cur.execute("SELECT 1 FROM schema_migrations WHERE name = %s", (name,))
    return cur.fetchone() is not None


def _mark_applied(cur, name: str) -> None:
    cur.execute(
        """
        INSERT INTO schema_migrations (name)
        VALUES (%s)
        ON CONFLICT (name) DO NOTHING
        """,
        (name,),
    )


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
    if not args.dry_run:
        _ensure_migration_table(cur)

    for name in MIGRATION_FILES:
        path = ROOT / "migrations" / name
        if not path.exists():
            print(f"SKIP missing {name}")
            continue
        if not args.dry_run and _already_applied(cur, name):
            print(f"SKIP already applied {name}")
            continue
        sql = path.read_text()
        print(f"{'[dry-run] ' if args.dry_run else ''}Applying {name}...")
        if not args.dry_run:
            try:
                cur.execute(sql)
                _mark_applied(cur, name)
            except Exception as exc:
                print(f"  WARN {name}: {exc}")
                conn.rollback()
                try:
                    cur.execute("ROLLBACK")
                except Exception:
                    pass

    if not args.dry_run:
        from database import ensure_schema_compat

        ensure_schema_compat()
        print("Ran ensure_schema_compat()")

    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
