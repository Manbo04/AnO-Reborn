#!/usr/bin/env python3
"""Diagnose login issues for a username (auth_type, hash columns, game data)."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from database import get_db_connection


def diagnose(username: str) -> None:
    pattern = f"%{username}%"
    with get_db_connection() as conn:
        db = conn.cursor()
        db.execute(
            """
            SELECT id, username, email, auth_type,
                   hash IS NOT NULL AS has_hash,
                   password IS NOT NULL AS has_password,
                   discord_id, recovery_key IS NOT NULL AS has_recovery,
                   is_verified
            FROM users
            WHERE username ILIKE %s OR username ILIKE %s
            """,
            (username, pattern),
        )
        rows = db.fetchall()
        if not rows:
            print(f"No users matching {username!r}")
            return
        for row in rows:
            uid = row[0]
            print("user:", row)
            db.execute(
                "SELECT COUNT(*) FROM stats WHERE id = %s",
                (uid,),
            )
            stats = db.fetchone()[0]
            db.execute(
                "SELECT COUNT(*) FROM provinces WHERE userid = %s",
                (uid,),
            )
            provinces = db.fetchone()[0]
            print(f"  stats_rows={stats} provinces={provinces}")


if __name__ == "__main__":
    diagnose(sys.argv[1] if len(sys.argv) > 1 else "levi")
