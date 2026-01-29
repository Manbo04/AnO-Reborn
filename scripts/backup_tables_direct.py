"""Direct dump of public tables to CSV files using psycopg2.connect.

This avoids importing project modules and is safe to run when database.get_db_cursor
can't be used (e.g., when cursor instrumentation prevents assignment to execute).

Usage: PYTHONPATH=. python3 scripts/backup_tables_direct.py
"""

import os
import time
import psycopg2

TS = time.strftime("%Y%m%d-%H%M%S")
OUTDIR = f"backups/reset-backup-{TS}-direct"
IGNORED_TABLES = set(["schema_migrations"])  # add more if needed
os.makedirs(OUTDIR, exist_ok=True)
print("Writing table CSVs to", OUTDIR)

# Read connection info from PG_* env vars
# (database.py already sets these from DATABASE_URL)
conn_params = {
    "dbname": os.getenv("PG_DATABASE"),
    "user": os.getenv("PG_USER"),
    "password": os.getenv("PG_PASSWORD"),
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5432")),
}

print("Connecting using:", {k: v for k, v in conn_params.items() if k != "password"})

try:
    conn = psycopg2.connect(**conn_params)
except Exception as e:
    print("Failed to connect to DB:", e)
    raise

try:
    cur = conn.cursor()
    cur.execute(
        (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE'"
        )
    )
    tables = [r[0] for r in cur.fetchall()]

    for table in tables:
        if table in IGNORED_TABLES:
            print("Skipping", table)
            continue
        outpath = os.path.join(OUTDIR, f"{table}.csv")
        try:
            with open(outpath, "w", encoding="utf-8") as f:
                print(f"Dumping {table} -> {outpath}")
                cur.copy_expert(f"COPY {table} TO STDOUT WITH CSV HEADER", f)
        except Exception as e:
            print(f"Failed to dump {table}: {e}")

    print("Done")
finally:
    try:
        cur.close()
    except Exception:
        pass
    conn.close()
