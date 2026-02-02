"""Cleanup script to remove legacy test accounts whose username starts with 'pa_test'

This script is intentionally conservative: it will only execute deletions when the
environment variable FORCE_DELETE is set to 'true'. This prevents accidental runs
against production DBs.

Usage:
  FORCE_DELETE=true python scripts/remove_test_accounts.py
"""

import os
from database import get_db_connection

FORCE = os.getenv("FORCE_DELETE", "false").lower() == "true"
if not FORCE:
    print(
        "Not deleting anything. To delete legacy test accounts, set FORCE_DELETE=true and re-run."
    )
    print(
        "This script will delete users with username LIKE 'pa_test%' but will NOT delete 'test_integration'."
    )
    raise SystemExit(0)

print("FORCE_DELETE=true detected — proceeding to remove legacy 'pa_test' accounts.")
with get_db_connection() as conn:
    db = conn.cursor()
    # Find user ids to delete (exclude canonical test_integration)
    db.execute(
        "SELECT id, username FROM users WHERE username LIKE %s AND username != %s",
        ("pa_test%", "test_integration"),
    )
    rows = db.fetchall()
    if not rows:
        print("No legacy test accounts found.")
    else:
        ids = [r[0] for r in rows]
        print(f"Found {len(ids)} legacy test users: {', '.join(r[1] for r in rows)}")
        # Delete dependent rows carefully
        for uid, uname in rows:
            print(f"Cleaning up user {uname} (id={uid})...")
            try:
                # Delete audit & revenue entries
                db.execute("DELETE FROM purchase_audit WHERE user_id=%s", (uid,))
                db.execute("DELETE FROM revenue WHERE user_id=%s", (uid,))
                # Remove province/infrastructure/stats/resources for provinces owned by this user
                db.execute("SELECT id FROM provinces WHERE userId=%s", (uid,))
                p_rows = db.fetchall()
                for pr in p_rows:
                    pid = pr[0]
                    db.execute("DELETE FROM proInfra WHERE id=%s", (pid,))
                    db.execute("DELETE FROM provinces WHERE id=%s", (pid,))
                db.execute("DELETE FROM stats WHERE id=%s", (uid,))
                db.execute("DELETE FROM resources WHERE id=%s", (uid,))
                # Finally delete the user
                db.execute("DELETE FROM users WHERE id=%s", (uid,))
                conn.commit()
                print(f"Deleted user {uname} and associated rows.")
            except Exception as e:
                conn.rollback()
                print(f"Failed to fully delete user {uname} (id={uid}): {e}")

print("Done.")
