"""
Assign join_number (early-adopter rank) to all users based on creation order.

This script:
1. Fetches all users ordered by created_at (earliest first)
2. Assigns sequential join_number values (1, 2, 3...)
3. Updates the database

The join_number serves as a public "Player #X" rank without exposing internal
user IDs.

Usage:
    python scripts/assign_join_ranks.py  [--dry-run]
    python scripts/assign_join_ranks.py  --commit
"""

import os
import sys
import argparse
import logging

import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
)
logger = logging.getLogger("assign_join_ranks")


def get_live_connection():
    """Connect to the live database."""
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        logger.error("Neither DATABASE_PUBLIC_URL nor DATABASE_URL is set.")
        sys.exit(1)
    return psycopg2.connect(url)


def check_column_exists(cur) -> bool:
    """Check if join_number column exists."""
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema='public' AND table_name='users' "
        "AND column_name='join_number'"
    )
    return cur.fetchone() is not None


def assign_join_ranks(cur, dry_run: bool) -> int:
    """
    Fetch all users ordered by creation date and assign join_number
    sequentially.
    """
    # Fetch all users ordered by creation date (earliest first)
    # The 'date' column stores sign-up time; order by join_number if already assigned,
    # then by date for new users
    cur.execute(
        "SELECT id, username, date FROM users "
        "WHERE date IS NOT NULL "
        "ORDER BY COALESCE(join_number, 999999), date::timestamp ASC"
    )
    users = cur.fetchall()

    if not users:
        logger.warning("No users found with created_at date.")
        return 0

    logger.info("Found %d users to rank.", len(users))

    if dry_run:
        logger.info("[DRY-RUN] Would assign join_number 1 to %d.", len(users))
        # Show first and last few users
        for idx, user in enumerate(users[:3], start=1):
            logger.info(
                "  [%d] join_number=%d, username=%s, date=%s",
                idx,
                idx,
                user["username"],
                user["date"],
            )
        if len(users) > 6:
            logger.info("  ...")
        for idx, user in enumerate(users[-3:], start=len(users) - 2):
            logger.info(
                "  [%d] join_number=%d, username=%s, date=%s",
                idx,
                idx,
                user["username"],
                user["date"],
            )
        return 0

    # Build update list: (join_number, user_id)
    updates = [
        {"join_number": rank, "user_id": user["id"]}
        for rank, user in enumerate(users, start=1)
    ]

    # Batch update all users
    update_sql = (
        "UPDATE users SET join_number = %(join_number)s " "WHERE id = %(user_id)s"
    )
    execute_batch(cur, update_sql, updates, page_size=500)

    logger.info("Assigned join_number to %d users.", len(users))
    return len(users)


def main():
    parser = argparse.ArgumentParser(
        description="Assign join_number (early-adopter rank) to all users."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually update the database (default is dry-run).",
    )
    args = parser.parse_args()
    dry_run = not args.commit

    if dry_run:
        logger.info("=== DRY-RUN MODE (pass --commit to update) ===")
    else:
        logger.warning("=== LIVE MODE — database will be UPDATED ===")

    conn = get_live_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if column exists first
            if not check_column_exists(cur):
                logger.error(
                    "join_number column does not exist. " "Run migration 0012 first."
                )
                sys.exit(1)

            num_assigned = assign_join_ranks(cur, dry_run)

        if dry_run:
            logger.info("Dry-run complete. Rolling back.")
            conn.rollback()
        else:
            conn.commit()
            logger.info(
                "Ranking complete — join_number assigned to %d users.", num_assigned
            )
    except Exception:
        conn.rollback()
        logger.exception("Assignment failed — rolled back.")
        sys.exit(1)
    finally:
        conn.close()

    return num_assigned


if __name__ == "__main__":
    main()
