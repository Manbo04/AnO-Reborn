#!/usr/bin/env python3
"""Apply migration 0023 (Discord guild panels)."""

from pathlib import Path

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_PUBLIC_URL or DATABASE_URL required")
    sql = (
        Path(__file__).resolve().parents[1]
        / "migrations"
        / "0023_discord_guild_panels.sql"
    ).read_text()
    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        conn.cursor().execute(sql)
        print("Applied 0023_discord_guild_panels.sql")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
