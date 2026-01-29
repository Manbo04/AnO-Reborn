"""
Safe user deletion utility for development/staging.
Usage:
    PYTHONPATH=. python scripts/delete_users.py username1 username2 ...

The script will:
 - Look up each username's id
 - Remove related rows (provinces + proInfra, stats, military, resources, upgrades,
   policies, market offers/trades, coalitions, col_applications, spyinfo, wars)
 - Finally delete the `users` row

This is intentionally conservative (deletes lots of related rows). Use with care.
"""

import sys

sys.path.append(".")
from dotenv import load_dotenv  # noqa: E402

load_dotenv()
from database import get_db_cursor  # noqa: E402


def delete_user_by_username(username: str):
    with get_db_cursor() as db:
        db.execute("SELECT id FROM users WHERE username=%s", (username,))
        row = db.fetchone()
        if not row:
            print(f"[skipped] user not found: {username}")
            return
        uid = row[0]
        print(f"Deleting user {username} (id={uid})")

        # Coalitions and related
        db.execute(
            "DELETE FROM col_applications WHERE userId=%s",
            (uid,),
        )
        db.execute(
            "DELETE FROM colBanks WHERE colId IN ("
            "SELECT colId FROM coalitions WHERE userId=%s)",
            (uid,),
        )
        db.execute("DELETE FROM coalitions WHERE userId=%s", (uid,))

        # Market
        db.execute("DELETE FROM offers WHERE user_id=%s", (uid,))
        db.execute("DELETE FROM trades WHERE offerer=%s OR offeree=%s", (uid, uid))

        # Wars and spyinfo
        db.execute("DELETE FROM wars WHERE attacker=%s OR defender=%s", (uid, uid))
        db.execute("DELETE FROM spyinfo WHERE spyer=%s OR spyee=%s", (uid, uid))

        # Upgrades/policies
        db.execute("DELETE FROM upgrades WHERE user_id=%s", (uid,))
        db.execute("DELETE FROM policies WHERE user_id=%s", (uid,))

        # Stats/military/resources
        db.execute("DELETE FROM stats WHERE id=%s", (uid,))
        db.execute("DELETE FROM military WHERE id=%s", (uid,))
        db.execute("DELETE FROM resources WHERE id=%s", (uid,))

        # Provinces + infra
        db.execute("SELECT id FROM provinces WHERE userId=%s", (uid,))
        provinces = db.fetchall()
        for pid_row in provinces:
            pid = pid_row[0]
            print(f"  - Deleting province {pid}")
            db.execute("DELETE FROM proInfra WHERE id=%s", (pid,))
            db.execute("DELETE FROM provinces WHERE id=%s", (pid,))

        # Finally delete the user row
        db.execute("DELETE FROM users WHERE id=%s", (uid,))
        print(f"Deleted user {username} and related data.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/delete_users.py username1 [username2 ...]")
        sys.exit(1)
    for uname in sys.argv[1:]:
        try:
            delete_user_by_username(uname)
        except Exception as e:
            print(f"Error deleting {uname}: {e}")
            raise
