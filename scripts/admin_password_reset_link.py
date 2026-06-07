#!/usr/bin/env python3
"""Generate a one-time password reset URL for support tickets.

Usage:
    python3 scripts/admin_password_reset_link.py --email user@example.com
    python3 scripts/admin_password_reset_link.py --username Primexia
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from change import generateResetCode, generateUrlFromCode
from database import get_db_cursor


def resolve_user_id(email: str | None, username: str | None) -> int | None:
    with get_db_cursor() as db:
        if email:
            db.execute("SELECT id FROM users WHERE lower(trim(email))=lower(trim(%s)) LIMIT 1", (email,))
        else:
            db.execute(
                "SELECT id FROM users WHERE trim(username)=trim(%s) LIMIT 1",
                (username,),
            )
        row = db.fetchone()
        return int(row[0]) if row else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Mint a one-time password reset link")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="Account email")
    group.add_argument("--username", help="Nation / country name")
    args = parser.parse_args()

    user_id = resolve_user_id(args.email, args.username)
    if user_id is None:
        print("No user found for the given email or username.", file=sys.stderr)
        return 1

    code = generateResetCode()
    created_at = int(datetime.now().timestamp())
    with get_db_cursor() as db:
        db.execute(
            """
            INSERT INTO reset_codes (url_code, user_id, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE
            SET url_code = EXCLUDED.url_code, created_at = EXCLUDED.created_at
            """,
            (code, user_id, created_at),
        )

    url = generateUrlFromCode(code)
    print(f"user_id={user_id}")
    print(url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
