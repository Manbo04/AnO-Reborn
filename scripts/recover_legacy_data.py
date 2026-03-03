"""
Recover legacy data from old wide tables into the new normalized schema.

Copies non-zero quantities from:
  resources       -> user_economy   (via resource_dictionary)
  military        -> user_military  (via unit_dictionary)
  proinfra        -> user_buildings (via building_dictionary)

Uses INSERT ... ON CONFLICT DO UPDATE so it is **idempotent** —
safe to run multiple times without creating duplicates.

Prerequisites:
  * The legacy tables (resources, military, proinfra) must still exist.
  * The dictionary tables must already be seeded.
  * DATABASE_PUBLIC_URL (or DATABASE_URL) env-var must be set.

Usage:
    python scripts/recover_legacy_data.py            # dry-run (default)
    python scripts/recover_legacy_data.py --commit   # actually write
"""

import os
import sys
import argparse
import logging

import psycopg2
from psycopg2.extras import RealDictCursor

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger("recover_legacy_data")

# Column-name → dictionary-name mappings.
# Keys are the exact column names in the legacy wide tables.
# Values are the corresponding `name` in the dictionary table.
# If a legacy column doesn't map to a dictionary entry it is skipped
# at runtime so the script stays forward-compatible.

RESOURCE_COLUMNS = [
    "rations",
    "oil",
    "coal",
    "uranium",
    "bauxite",
    "iron",
    "lead",
    "copper",
    "lumber",
    "components",
    "steel",
    "consumer_goods",
    "aluminium",
    "gasoline",
    "ammunition",
]

# The old military table used these column names for unit counts.
# 'ICBMs' was stored as mixed-case in some schemas; we normalise to
# lower-case when looking up unit_dictionary.
MILITARY_COLUMNS = {
    "soldiers": "soldiers",
    "tanks": "tanks",
    "artillery": "artillery",
    "fighters": "fighters",
    "bombers": "bombers",
    "destroyers": "destroyers",
    "cruisers": "cruisers",
    "submarines": "submarines",
    "spies": "spies",
    "ICBMs": "icbms",
    "nukes": "nukes",
    "apaches": "apaches",
}

# proInfra columns → building_dictionary names.
# Some legacy columns may not exist in building_dictionary yet
# (e.g. gas_stations, farmers_markets, monorails, admin_buildings,
# aerodomes, silos).  They are included for completeness; the
# script skips any that have no dictionary match.
BUILDING_COLUMNS = [
    "farms",
    "pumpjacks",
    "coal_mines",
    "steel_mills",
    "coal_burners",
    "oil_burners",
    "nuclear_reactors",
    "hospitals",
    "universities",
    "libraries",
    "general_stores",
    "malls",
    "banks",
    "army_bases",
    "aerodromes",
    "harbours",
    # Additional legacy buildings (may or may not be in dictionary)
    "gas_stations",
    "farmers_markets",
    "monorails",
    "admin_buildings",
    "aerodomes",
    "silos",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def get_connection():
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        logger.error("Neither DATABASE_PUBLIC_URL nor DATABASE_URL is set.")
        sys.exit(1)
    return psycopg2.connect(url)


def table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table_name,),
    )
    return cur.fetchone() is not None


def get_table_columns(cur, table_name: str) -> set:
    """Return the set of column names that actually exist on *table_name*."""
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table_name,),
    )
    return {row[0] for row in cur.fetchall()}


def load_dictionary(cur, table: str, id_col: str, name_col: str):
    """Return {name: id} mapping from a dictionary table."""
    cur.execute(f"SELECT {id_col}, {name_col} FROM {table}")
    return {row[name_col]: row[id_col] for row in cur.fetchall()}


# ---------------------------------------------------------------------------
# Migration functions
# ---------------------------------------------------------------------------


def migrate_resources(cur, dry_run: bool):
    """resources table → user_economy."""
    if not table_exists(cur, "resources"):
        logger.warning("Legacy table 'resources' does not exist — skipping.")
        return

    name_to_id = load_dictionary(cur, "resource_dictionary", "resource_id", "name")
    actual_cols = get_table_columns(cur, "resources")

    # Build the list of (column, resource_id) pairs we can migrate
    pairs = []
    for col in RESOURCE_COLUMNS:
        if col not in actual_cols:
            logger.info("resources.%s not present — skipping.", col)
            continue
        rid = name_to_id.get(col)
        if rid is None:
            logger.info("No resource_dictionary entry for '%s' — skipping.", col)
            continue
        pairs.append((col, rid))

    if not pairs:
        logger.warning("No mappable resource columns found.")
        return

    # Build a dynamic SELECT that unpivots all columns in one pass
    # Result: rows of (user_id, resource_id, quantity)
    select_parts = []
    for col, rid in pairs:
        select_parts.append(
            f"SELECT id AS user_id, {rid} AS resource_id, "
            f'COALESCE("{col}", 0) AS quantity FROM resources '
            f'WHERE COALESCE("{col}", 0) > 0'
        )
    union_sql = " UNION ALL ".join(select_parts)

    upsert_sql = f"""
        INSERT INTO user_economy (user_id, resource_id, quantity, updated_at)
        SELECT user_id, resource_id, quantity, now()
        FROM ({union_sql}) AS legacy
        ON CONFLICT (user_id, resource_id)
        DO UPDATE SET
            quantity = GREATEST(user_economy.quantity, EXCLUDED.quantity),
            updated_at = now()
    """

    logger.info("Migrating resources: %d columns for all users...", len(pairs))
    if dry_run:
        logger.info("[DRY-RUN] Would execute resources upsert.")
    else:
        cur.execute(upsert_sql)
        logger.info(
            "Resources upsert complete — %d rows affected.",
            cur.rowcount,
        )


def migrate_military(cur, dry_run: bool):
    """military table → user_military."""
    if not table_exists(cur, "military"):
        logger.warning("Legacy table 'military' does not exist — skipping.")
        return

    name_to_id = load_dictionary(cur, "unit_dictionary", "unit_id", "name")
    actual_cols = get_table_columns(cur, "military")

    pairs = []
    for col, dict_name in MILITARY_COLUMNS.items():
        if col.lower() not in {c.lower() for c in actual_cols}:
            logger.info("military.%s not present — skipping.", col)
            continue
        uid = name_to_id.get(dict_name)
        if uid is None:
            logger.info("No unit_dictionary entry for '%s' — skipping.", dict_name)
            continue
        pairs.append((col, uid))

    if not pairs:
        logger.warning("No mappable military columns found.")
        return

    select_parts = []
    for col, uid in pairs:
        select_parts.append(
            f"SELECT id AS user_id, {uid} AS unit_id, "
            f'COALESCE("{col}", 0) AS quantity FROM military '
            f'WHERE COALESCE("{col}", 0) > 0'
        )
    union_sql = " UNION ALL ".join(select_parts)

    upsert_sql = f"""
        INSERT INTO user_military (user_id, unit_id, quantity, updated_at)
        SELECT user_id, unit_id, quantity, now()
        FROM ({union_sql}) AS legacy
        ON CONFLICT (user_id, unit_id)
        DO UPDATE SET
            quantity = GREATEST(user_military.quantity, EXCLUDED.quantity),
            updated_at = now()
    """

    logger.info("Migrating military: %d columns for all users...", len(pairs))
    if dry_run:
        logger.info("[DRY-RUN] Would execute military upsert.")
    else:
        cur.execute(upsert_sql)
        logger.info(
            "Military upsert complete — %d rows affected.",
            cur.rowcount,
        )


def migrate_buildings(cur, dry_run: bool):
    """proinfra table → user_buildings."""
    if not table_exists(cur, "proinfra"):
        logger.warning("Legacy table 'proinfra' does not exist — skipping.")
        return

    name_to_id = load_dictionary(cur, "building_dictionary", "building_id", "name")
    actual_cols = get_table_columns(cur, "proinfra")

    pairs = []
    for col in BUILDING_COLUMNS:
        if col not in actual_cols:
            logger.info("proinfra.%s not present — skipping.", col)
            continue
        bid = name_to_id.get(col)
        if bid is None:
            logger.info("No building_dictionary entry for '%s' — skipping.", col)
            continue
        pairs.append((col, bid))

    if not pairs:
        logger.warning("No mappable building columns found.")
        return

    # proinfra is per-province (has a province / userId key).
    # user_buildings is per-user, so we SUM across provinces.
    select_parts = []
    for col, bid in pairs:
        select_parts.append(
            f'SELECT "userId" AS user_id, {bid} AS building_id, '
            f'SUM(COALESCE("{col}", 0)) AS quantity '
            f"FROM proinfra "
            f'GROUP BY "userId" '
            f'HAVING SUM(COALESCE("{col}", 0)) > 0'
        )
    union_sql = " UNION ALL ".join(select_parts)

    upsert_sql = f"""
        INSERT INTO user_buildings (user_id, building_id, quantity, updated_at)
        SELECT user_id, building_id, quantity, now()
        FROM ({union_sql}) AS legacy
        ON CONFLICT (user_id, building_id)
        DO UPDATE SET
            quantity = GREATEST(
                user_buildings.quantity, EXCLUDED.quantity
            ),
            updated_at = now()
    """

    logger.info("Migrating buildings: %d columns for all users...", len(pairs))
    if dry_run:
        logger.info("[DRY-RUN] Would execute buildings upsert.")
    else:
        cur.execute(upsert_sql)
        logger.info(
            "Buildings upsert complete — %d rows affected.",
            cur.rowcount,
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Recover legacy data into normalized tables."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually write to the database (default is dry-run).",
    )
    args = parser.parse_args()
    dry_run = not args.commit

    if dry_run:
        logger.info("=== DRY-RUN MODE (pass --commit to write) ===")
    else:
        logger.info("=== LIVE MODE — changes will be committed ===")

    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            migrate_resources(cur, dry_run)
            migrate_military(cur, dry_run)
            migrate_buildings(cur, dry_run)

        if dry_run:
            logger.info("Dry-run complete. Rolling back.")
            conn.rollback()
        else:
            conn.commit()
            logger.info("All migrations committed successfully.")
    except Exception:
        conn.rollback()
        logger.exception("Migration failed — rolled back.")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
