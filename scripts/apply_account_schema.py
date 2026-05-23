#!/usr/bin/env python3
"""Ensure users columns required by /account (discord_id, recovery_key)."""

from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: Set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)

    statements = [
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS discord_id VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS recovery_key VARCHAR(255)",
    ]

    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for sql in statements:
                print(f"Running: {sql[:60]}...")
                cur.execute(sql)
        print("Done.")
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
