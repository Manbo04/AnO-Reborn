"""Soft-deactivate user accounts (non-destructive).

Usage:
    python scripts/soft_deactivate_users.py --dry-run
    python scripts/soft_deactivate_users.py --execute

By default excludes users with role='admin'.
"""

import argparse
import datetime
from src.database import get_db_connection


def run(dry_run=True, exclude_admins=True):
    exclude_clause = " AND role != 'admin'" if exclude_admins else ""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, username, email FROM users "
            "WHERE is_active IS DISTINCT FROM FALSE" + exclude_clause
        )
        rows = cur.fetchall()
        print(f"Found {len(rows)} user(s) that would be soft-deactivated")
        if dry_run:
            for r in rows[:20]:
                print(r)
            return
        now = datetime.datetime.utcnow()
        cur.execute(
            "UPDATE users SET is_active = FALSE, reset_required = TRUE, "
            "reset_at = %s WHERE is_active IS DISTINCT FROM FALSE" + exclude_clause,
            (now,),
        )
        conn.commit()
        print(f"Soft-deactivated {len(rows)} users.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--exclude-admins", dest="exclude_admins", action="store_true", default=True
    )
    args = parser.parse_args()
    run(dry_run=not args.execute, exclude_admins=args.exclude_admins)
