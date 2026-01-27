"""Dump all public tables to CSV files under backups/reset-backup-<timestamp>/

Usage:
  PYTHONPATH=. venv310/bin/python scripts/backup_tables.py

This uses the app's DB connection (database.get_db_connection/get_db_cursor) and
writes one CSV file per table. It will skip some internal tables if needed.
"""

import os
import time
from src.database import get_db_cursor

TS = time.strftime("%Y%m%d-%H%M%S")
OUTDIR = f"backups/reset-backup-{TS}"
IGNORED_TABLES = set(["schema_migrations"])  # add more if needed

os.makedirs(OUTDIR, exist_ok=True)
print("Writing table CSVs to", OUTDIR)

with get_db_cursor() as db:
    db.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='public' AND table_type='BASE TABLE'"
    )
    tables = [r[0] for r in db.fetchall()]

    for table in tables:
        if table in IGNORED_TABLES:
            print("Skipping", table)
            continue
        outpath = os.path.join(OUTDIR, f"{table}.csv")
        try:
            with open(outpath, "w", encoding="utf-8") as f:
                print(f"Dumping {table} -> {outpath}")
                db.copy_expert(f"COPY {table} TO STDOUT WITH CSV HEADER", f)
        except Exception as e:
            print(f"Failed to dump {table}: {e}")

print("Done")
