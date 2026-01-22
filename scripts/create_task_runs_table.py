#!/usr/bin/env python3
"""Ensure the `task_runs` table exists.

Run this in production once after deployment to avoid race conditions where tasks
try to `CREATE TABLE IF NOT EXISTS` concurrently.
"""
from database import get_db_connection

if __name__ == "__main__":
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS task_runs (
                task_name TEXT PRIMARY KEY,
                last_run TIMESTAMP WITH TIME ZONE
            );
            """
        )
        conn.commit()
    print("task_runs table ensured")
