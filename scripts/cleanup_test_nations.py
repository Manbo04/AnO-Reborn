"""
Clean up test nations from the live database.

Deletes all users where the username starts with "provtest_" and all
their associated data via cascading deletes.

This includes:
  - User accounts and stats
  - All provinces
  - Military, resources, buildings (cascades from provinces)
  - Wars, treaties, trades (most cascade via user or province FKs)
  - Coalition memberships and related data

Prerequisites:
  DATABASE_URL env-var must be set (from .env)

Usage:
    python scripts/cleanup_test_nations.py  [--dry-run]
    python scripts/cleanup_test_nations.py  --commit
"""

import os
import sys
import argparse
import logging

import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
)
logger = logging.getLogger("cleanup_test_nations")


def get_live_connection():
    """Connect to the live database."""
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        logger.error("Neither DATABASE_PUBLIC_URL nor DATABASE_URL is set.")
        sys.exit(1)
    return psycopg2.connect(url)


def get_test_user_ids(cur) -> list:
    """Get all user IDs where username starts with 'provtest_'."""
    cur.execute(
        "SELECT id, username FROM users WHERE username LIKE %s", ("provtest_%",)
    )
    return cur.fetchall()


def cleanup_user(cur, user_id: int, username: str, dry_run: bool) -> int:
    """
    Delete a test user. All related records cascade-delete via FK constraints.
    """

    if dry_run:
        logger.info(
            "  [DRY-RUN] Would delete user %d (%s) and cascaded data", user_id, username
        )
        return 0

    try:
        # Delete from users - FK cascades should handle everything else
        cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
        deleted_count = cur.rowcount

        logger.info("Deleted user %d (%s)", user_id, username)
        return deleted_count
    except psycopg2.Error as e:
        logger.error(
            "Error deleting user %d (%s): %s — rolling back",
            user_id,
            username,
            e,
        )
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Clean up test nations from the live database."
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually delete from the database (default is dry-run).",
    )
    args = parser.parse_args()
    dry_run = not args.commit

    if dry_run:
        logger.info("=== DRY-RUN MODE (pass --commit to delete) ===")
    else:
        logger.warning("=== LIVE MODE — data will be PERMANENTLY DELETED ===")

    conn = get_live_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            test_users = get_test_user_ids(cur)

            if not test_users:
                logger.info("No test users found matching pattern 'provtest_*'.")
                conn.close()
                return 0

            logger.info(
                "Found %d test user(s): %s",
                len(test_users),
                ", ".join(u["username"] for u in test_users),
            )

            total_deleted = 0
            for user in test_users:
                count = cleanup_user(cur, user["id"], user["username"], dry_run)
                total_deleted += count

        if dry_run:
            logger.info("Dry-run complete. Rolling back.")
            conn.rollback()
        else:
            conn.commit()
            logger.info(
                "Cleanup complete — %d test users deleted "
                "(cascaded to all related records).",
                len(test_users),
            )
    except Exception:
        conn.rollback()
        logger.exception("Cleanup failed — rolled back.")
        sys.exit(1)
    finally:
        conn.close()

    return len(test_users)


if __name__ == "__main__":
    num_deleted = main()
    sys.exit(0 if num_deleted == 0 else 0)
