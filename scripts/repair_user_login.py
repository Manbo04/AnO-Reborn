#!/usr/bin/env python3
"""Repair legacy user login: auth_type, password hash columns, missing game data."""

import argparse
import os
import sys

import bcrypt

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from database import get_db_connection, set_user_password
from signup import init_user_game_data


def repair(username: str, new_password: str | None, continent: str = "europe") -> bool:
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            "SELECT id, username, auth_type FROM users WHERE username ILIKE %s",
            (username,),
        )
        row = db.fetchone()
        if not row:
            print(f"User {username!r} not found")
            return False

        user_id, db_username, auth_type = row
        print(f"Found user id={user_id} username={db_username!r} auth_type={auth_type!r}")

        if auth_type is None or auth_type == "":
            db.execute(
                "UPDATE users SET auth_type = 'normal' WHERE id = %s",
                (user_id,),
            )
            print("Set auth_type='normal'")

        db.execute("SELECT COUNT(*) FROM stats WHERE id = %s", (user_id,))
        has_stats = db.fetchone()[0] > 0
        db.execute("SELECT COUNT(*) FROM provinces WHERE userid = %s", (user_id,))
        has_provinces = db.fetchone()[0] > 0

        if not has_stats or not has_provinces:
            init_user_game_data(db, user_id, continent)
            print(f"Initialized game data (stats={has_stats}, provinces={has_provinces})")

        if new_password:
            hashed = bcrypt.hashpw(
                new_password.encode("utf-8"), bcrypt.gensalt(14)
            ).decode("utf-8")
            set_user_password(db, user_id, hashed)
            print("Password updated via set_user_password (hash + password columns)")

        conn.commit()
        print(f"Repair complete for {db_username}")
        return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("username")
    parser.add_argument("--password", help="Set new password (optional)")
    parser.add_argument("--continent", default="europe")
    args = parser.parse_args()
    ok = repair(args.username, args.password, args.continent)
    sys.exit(0 if ok else 1)
