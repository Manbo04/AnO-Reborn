#!/usr/bin/env python3
"""Run simple DB diagnostics using DATABASE_PUBLIC_URL env var.
Prints: max_connections, counts by state, top 10 longest non-idle queries,
and top pg_stat_statements if available.
"""
import os
import sys
import traceback

try:
    import psycopg2
except Exception:
    print("psycopg2 not available; install it in the container to run this script.")
    sys.exit(2)

url = os.environ.get("DATABASE_PUBLIC_URL")
if not url:
    print("DATABASE_PUBLIC_URL not set in environment")
    sys.exit(3)

try:
    conn = psycopg2.connect(url)
    cur = conn.cursor()

    cur.execute("SHOW max_connections;")
    print("max_connections:", cur.fetchone())

    cur.execute("SELECT count(*) FROM pg_stat_activity;")
    print("active connections:", cur.fetchone())

    cur.execute("SELECT state, count(*) FROM pg_stat_activity GROUP BY state;")
    print("states:")
    for row in cur.fetchall():
        print(" ", row)

    cur.execute(
        """
        SELECT pid, usename, state, now() - query_start AS duration, left(query, 500)
        FROM pg_stat_activity
        WHERE state <> 'idle' AND query <> '<IDLE>'
        ORDER BY duration DESC
        LIMIT 20;
        """
    )
    rows = cur.fetchall()
    print("\nTop non-idle queries (by duration):")
    for r in rows:
        print(r)

    # Try pg_stat_statements summary if available
    try:
        cur.execute(
            """
            SELECT query, calls, total_time, mean_time
            FROM pg_stat_statements
            ORDER BY total_time DESC
            LIMIT 10;
            """
        )
        print("\nTop pg_stat_statements:")
        for r in cur.fetchall():
            print(r)
    except Exception:
        print("pg_stat_statements not available or permission denied")

    cur.close()
    conn.close()
except Exception:
    traceback.print_exc()
    sys.exit(1)
