"""Hard delete non-admin users with dry-run support.

Usage:
    python scripts/hard_delete_nonadmins.py --dry-run
    python scripts/hard_delete_nonadmins.py --execute --exclude-admins

WARNING: destructive. Do not run without backups and explicit approval.
"""

import argparse
from src.database import get_db_connection


def run(dry_run=True, exclude_admins=True):
    exclude_clause = " AND role != 'admin'" if exclude_admins else ""
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, username, email FROM users WHERE 1=1" + exclude_clause)
        rows = cur.fetchall()
        print(f"Would delete {len(rows)} users")
        if dry_run:
            for r in rows[:20]:
                print(r)
            return
        ids = [r[0] for r in rows]
        # Archive to deleted_users table if present (best-effort)
        try:
            cur.execute(
                """
                INSERT INTO deleted_users (user_id, username, email, deleted_at)
                SELECT id, username, email, NOW() FROM users WHERE id = ANY(%s)
                """,
                (ids,),
            )
        except Exception:
            pass
        cur.execute("DELETE FROM users WHERE id = ANY(%s)", (ids,))
        conn.commit()
        print(f"Deleted {len(ids)} users")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument(
        "--exclude-admins", dest="exclude_admins", action="store_true", default=True
    )
    args = parser.parse_args()
    run(dry_run=not args.execute, exclude_admins=args.exclude_admins)
