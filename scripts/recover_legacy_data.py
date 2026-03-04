"""
Recover legacy data from old wide tables into the new normalized schema.

Reads from a **backup** database (BACKUP_DATABASE_URL) and writes into the
**live** database (DATABASE_PUBLIC_URL / DATABASE_URL).

Copies non-zero quantities from:
  resources       -> user_economy   (via resource_dictionary)
  military        -> user_military  (via unit_dictionary)
  proinfra        -> user_buildings (via building_dictionary)

Uses INSERT ... ON CONFLICT DO UPDATE so it is **idempotent** —
safe to run multiple times without creating duplicates.

Prerequisites:
  * BACKUP_DATABASE_URL must point to a DB that still has the legacy
    wide tables (resources, military, proinfra).
  * DATABASE_PUBLIC_URL (or DATABASE_URL) must point to the live DB
    with the normalized schema and seeded dictionary tables.

Usage:
    python scripts/recover_legacy_data.py            # dry-run (default)
    python scripts/recover_legacy_data.py --commit   # actually write
"""

import os
import sys
import argparse
import logging

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

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


def get_backup_connection():
    """Connect to the backup DB that still has legacy wide tables."""
    url = os.getenv("BACKUP_DATABASE_URL")
    if not url:
        logger.error("BACKUP_DATABASE_URL is not set.")
        sys.exit(1)
    return psycopg2.connect(url)


def get_live_connection():
    """Connect to the live DB with the normalized schema."""
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
    return {row["column_name"] for row in cur.fetchall()}


def load_dictionary(cur, table: str, id_col: str, name_col: str):
    """Return {name: id} mapping from a dictionary table."""
    cur.execute(f"SELECT {id_col}, {name_col} FROM {table}")
    return {row[name_col]: row[id_col] for row in cur.fetchall()}


def get_valid_user_ids(cur) -> set:
    """Return the set of all user IDs that exist in the live users table."""
    cur.execute("SELECT id FROM users")
    return {row["id"] for row in cur.fetchall()}


def find_user_id_column(actual_cols: set) -> str | None:
    """
    Find the user ID column in the given set of column names (case-insensitive).
    Expected names: userId, user_id, userid.
    """
    for expected_name in ["userId", "user_id", "userid"]:
        for col in actual_cols:
            if col.lower() == expected_name.lower():
                return col
    return None


def find_actual_column_name(expected: str, actual_cols: set) -> str | None:
    """
    Find the actual column name in the table that matches expected (case-insensitive).
    Returns the actual column name, or None if not found.
    """
    expected_lower = expected.lower()
    for col in actual_cols:
        if col.lower() == expected_lower:
            return col
    return None


# ---------------------------------------------------------------------------
# Migration functions
#
# Each function takes TWO cursors:
#   backup_cur – reads from the legacy wide tables (backup DB)
#   live_cur   – writes into the normalized tables (live DB)
# Dictionary lookups use live_cur (dictionaries are on live DB).
# ---------------------------------------------------------------------------

UPSERT_BATCH_SIZE = 500


def migrate_resources(backup_cur, live_cur, dry_run: bool):
    """resources table → user_economy."""
    if not table_exists(backup_cur, "resources"):
        logger.warning("Legacy table 'resources' does not exist on backup — skipping.")
        return

    name_to_id = load_dictionary(live_cur, "resource_dictionary", "resource_id", "name")
    actual_cols = get_table_columns(backup_cur, "resources")

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

    # Read legacy data from backup into memory
    select_parts = []
    for col, rid in pairs:
        select_parts.append(
            f"SELECT id AS user_id, {rid} AS resource_id, "
            f'COALESCE("{col}", 0) AS quantity FROM resources '
            f'WHERE COALESCE("{col}", 0) > 0'
        )
    union_sql = " UNION ALL ".join(select_parts)
    backup_cur.execute(union_sql)
    all_rows = backup_cur.fetchall()

    # Filter to only users that exist in the live database
    valid_user_ids = get_valid_user_ids(live_cur)
    rows = [r for r in all_rows if r["user_id"] in valid_user_ids]

    logger.info(
        "Migrating resources: %d columns, %d total rows from backup...",
        len(pairs),
        len(rows),
    )
    if len(rows) < len(all_rows):
        logger.info(
            "Filtered out %d rows for non-existent users.",
            len(all_rows) - len(rows),
        )

    if not rows:
        logger.warning("No non-zero resource rows found in backup.")
        return

    if dry_run:
        logger.info("[DRY-RUN] Would upsert %d resource rows.", len(rows))
        return

    upsert_sql = """
        INSERT INTO user_economy (user_id, resource_id, quantity, updated_at)
        VALUES (%(user_id)s, %(resource_id)s, %(quantity)s, now())
        ON CONFLICT (user_id, resource_id)
        DO UPDATE SET
            quantity = GREATEST(user_economy.quantity, EXCLUDED.quantity),
            updated_at = now()
    """
    execute_batch(live_cur, upsert_sql, rows, page_size=UPSERT_BATCH_SIZE)
    logger.info("Resources upsert complete — %d rows processed.", len(rows))


def migrate_military(backup_cur, live_cur, dry_run: bool):
    """military table → user_military."""
    if not table_exists(backup_cur, "military"):
        logger.warning("Legacy table 'military' does not exist on backup — skipping.")
        return

    name_to_id = load_dictionary(live_cur, "unit_dictionary", "unit_id", "name")
    actual_cols = get_table_columns(backup_cur, "military")

    pairs = []
    for col, dict_name in MILITARY_COLUMNS.items():
        actual_col = find_actual_column_name(col, actual_cols)
        if not actual_col:
            logger.info("military.%s not present — skipping.", col)
            continue
        uid = name_to_id.get(dict_name)
        if uid is None:
            logger.info("No unit_dictionary entry for '%s' — skipping.", dict_name)
            continue
        pairs.append((actual_col, uid))

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
    backup_cur.execute(union_sql)
    all_rows = backup_cur.fetchall()

    # Filter to only users that exist in the live database
    valid_user_ids = get_valid_user_ids(live_cur)
    rows = [r for r in all_rows if r["user_id"] in valid_user_ids]

    logger.info(
        "Migrating military: %d columns, %d total rows from backup...",
        len(pairs),
        len(rows),
    )
    if len(rows) < len(all_rows):
        logger.info(
            "Filtered out %d rows for non-existent users.",
            len(all_rows) - len(rows),
        )

    if not rows:
        logger.warning("No non-zero military rows found in backup.")
        return

    if dry_run:
        logger.info("[DRY-RUN] Would upsert %d military rows.", len(rows))
        return

    upsert_sql = """
        INSERT INTO user_military (user_id, unit_id, quantity, updated_at)
        VALUES (%(user_id)s, %(unit_id)s, %(quantity)s, now())
        ON CONFLICT (user_id, unit_id)
        DO UPDATE SET
            quantity = GREATEST(user_military.quantity, EXCLUDED.quantity),
            updated_at = now()
    """
    execute_batch(live_cur, upsert_sql, rows, page_size=UPSERT_BATCH_SIZE)
    logger.info("Military upsert complete — %d rows processed.", len(rows))


def migrate_buildings(backup_cur, live_cur, dry_run: bool):
    """proinfra table → user_buildings."""
    if not table_exists(backup_cur, "proinfra"):
        logger.warning("Legacy table 'proinfra' does not exist on backup — skipping.")
        return

    name_to_id = load_dictionary(live_cur, "building_dictionary", "building_id", "name")
    actual_cols = get_table_columns(backup_cur, "proinfra")

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

    # proinfra is per-province; user_buildings is per-user → SUM.
    # Join proinfra → provinces to get the user ID
    select_parts = []
    for col, bid in pairs:
        select_parts.append(
            f"SELECT provinces.userid AS user_id, {bid} AS building_id, "
            f'SUM(COALESCE(proinfra."{col}", 0)) AS quantity '
            f"FROM proinfra "
            f"JOIN provinces ON proinfra.id = provinces.id "
            f"GROUP BY provinces.userid "
            f'HAVING SUM(COALESCE(proinfra."{col}", 0)) > 0'
        )
    union_sql = " UNION ALL ".join(select_parts)
    backup_cur.execute(union_sql)
    all_rows = backup_cur.fetchall()

    # Filter to only users that exist in the live database
    valid_user_ids = get_valid_user_ids(live_cur)
    rows = [r for r in all_rows if r["user_id"] in valid_user_ids]

    logger.info(
        "Migrating buildings: %d columns, %d total rows from backup...",
        len(pairs),
        len(rows),
    )
    if len(rows) < len(all_rows):
        logger.info(
            "Filtered out %d rows for non-existent users.",
            len(all_rows) - len(rows),
        )

    if not rows:
        logger.warning("No non-zero building rows found in backup.")
        return

    if dry_run:
        logger.info("[DRY-RUN] Would upsert %d building rows.", len(rows))
        return

    upsert_sql = """
        INSERT INTO user_buildings (user_id, building_id, quantity)
        VALUES (%(user_id)s, %(building_id)s, %(quantity)s)
        ON CONFLICT (user_id, building_id)
        DO UPDATE SET
            quantity = GREATEST(
                user_buildings.quantity, EXCLUDED.quantity
            )
    """
    execute_batch(live_cur, upsert_sql, rows, page_size=UPSERT_BATCH_SIZE)
    logger.info("Buildings upsert complete — %d rows processed.", len(rows))


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

    backup_conn = get_backup_connection()
    live_conn = get_live_connection()
    try:
        with backup_conn.cursor(
            cursor_factory=RealDictCursor
        ) as backup_cur, live_conn.cursor(cursor_factory=RealDictCursor) as live_cur:
            migrate_resources(backup_cur, live_cur, dry_run)
            migrate_military(backup_cur, live_cur, dry_run)
            migrate_buildings(backup_cur, live_cur, dry_run)

        if dry_run:
            logger.info("Dry-run complete. Rolling back.")
            live_conn.rollback()
        else:
            live_conn.commit()
            logger.info("All migrations committed successfully.")
    except Exception:
        live_conn.rollback()
        logger.exception("Migration failed — rolled back.")
        sys.exit(1)
    finally:
        backup_conn.close()
        live_conn.close()


if __name__ == "__main__":
    main()
