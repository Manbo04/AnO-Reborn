#!/usr/bin/env python3
"""Load db/schema.sql + reference_data.sql + test_seed.sql into an EMPTY test database.

Used by CI (and locally) so tests and the SQL schema check run against the
real production schema instead of a hand-built approximation.

Refuses to touch anything that looks like a hosted/production database:
it drops and recreates the public schema.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5432/anodb \
        python scripts/load_schema_snapshot.py
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "postgres"}


def main() -> int:
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        print("ERROR: set DATABASE_URL to a local, disposable database")
        return 2
    host = urlparse(dsn).hostname or ""
    if host not in LOCAL_HOSTS:
        print(f"REFUSING: {host!r} is not a local database. This script wipes the schema.")
        return 2

    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;")
    # test_seed.sql adds two synthetic fixed accounts (ids 1 and 16) that tests
    # assume exist, as they do in production.
    for name in ("schema.sql", "reference_data.sql", "test_seed.sql"):
        cur.execute((ROOT / "db" / name).read_text(encoding="utf-8"))
        # pg_dump output empties search_path for the session; restore it.
        cur.execute("SET search_path TO public")
        print(f"loaded db/{name}")
    cur.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
    )
    print(f"tables: {cur.fetchone()[0]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
