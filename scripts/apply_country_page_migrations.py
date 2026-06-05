#!/usr/bin/env python3
"""Apply idempotent SQL migrations required for the country page (0011–0013).

Usage:
    DATABASE_PUBLIC_URL=postgresql://... python3 scripts/apply_country_page_migrations.py
"""


import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = [
    ROOT / "migrations" / "0011_add_users_last_active.sql",
    ROOT / "migrations" / "0012_add_join_number.sql",
    ROOT / "migrations" / "0013_add_demographics_education_schema.sql",
]


def main() -> None:
    import psycopg2

    url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not url:
        print("ERROR: Set DATABASE_PUBLIC_URL or DATABASE_URL")
        sys.exit(1)

    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for path in MIGRATIONS:
                if not path.exists():
                    print(f"SKIP missing file: {path}")
                    continue
                sql = path.read_text()
                print(f"Applying {path.name}...")
                cur.execute(sql)
                print(f"  OK {path.name}")
        print("Done. Run: python3 scripts/assign_join_ranks.py")
    except Exception as exc:
        print(f"FAILED: {exc}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
