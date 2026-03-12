#!/usr/bin/env python3
"""Apply migration 0018: cleanup duplicate indexes, add spyinfo compound index."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if not db_url:
    print("ERROR: No DATABASE_URL or DATABASE_PUBLIC_URL set")
    exit(1)

migration_path = os.path.join(
    os.path.dirname(__file__),
    "..",
    "migrations",
    "0018_cleanup_indexes_add_spyinfo.sql",
)
with open(migration_path) as f:
    sql = f.read()

conn = psycopg2.connect(db_url)
conn.autocommit = True
cur = conn.cursor()

for statement in sql.split(";"):
    statement = statement.strip()
    if not statement or statement.startswith("--"):
        continue
    # Filter out pure comment blocks
    lines = [
        ln
        for ln in statement.split("\n")
        if ln.strip() and not ln.strip().startswith("--")
    ]
    if not lines:
        continue
    try:
        cur.execute(statement)
        print(f"OK: {statement[:60]}...")
    except Exception as e:
        print(f"SKIP: {e}")

cur.close()
conn.close()
print("Migration 0018 applied.")
