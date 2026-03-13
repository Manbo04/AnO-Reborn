#!/usr/bin/env python3
"""Apply migration 0020: Enforce population/demographics sync via DB trigger.

Usage:
    DATABASE_PUBLIC_URL=... python3 scripts/apply_migration_0020.py
"""

import os
import sys

import psycopg2

db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if not db_url:
    print("ERROR: No DATABASE_URL or DATABASE_PUBLIC_URL set")
    sys.exit(1)

conn = psycopg2.connect(db_url)
conn.autocommit = False
cur = conn.cursor()

migration_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "migrations",
    "0020_enforce_population_demographics_sync.sql",
)

with open(migration_path) as f:
    sql = f.read()

print("Applying migration 0020: enforce population/demographics sync...")
try:
    cur.execute(sql)
    conn.commit()
    print("Migration applied successfully.")
except Exception as e:
    conn.rollback()
    print(f"ERROR: {e}")
    sys.exit(1)
finally:
    cur.close()
    conn.close()
