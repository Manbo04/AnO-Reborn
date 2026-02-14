#!/usr/bin/env python3
"""Dump recent province deletion audit rows from the production DB.

Usage:
  PYTHONPATH=. python3 scripts/audit_province_deletes.py --hours 24 --out recent_deletes.json

Writes JSON and CSV with rows from admin_actions where action in
('province_deleted','delete_provinces') within the given timeframe.
"""
import argparse
import json
import csv
import os
from datetime import datetime, timedelta

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    print("psycopg2 is required: pip install psycopg2-binary")
    raise


def dump_rows(conn, hours):
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, actor, action, user_id, details, to_char(created_at, 'YYYY-MM-DD HH24:MI:SS') AS created_at
            FROM admin_actions
            WHERE action IN ('province_deleted','delete_provinces') AND created_at > now() - interval '%s hours'
            ORDER BY created_at DESC
            """,
            (hours,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return rows


def write_json(path, rows):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, default=str)


def write_csv(path, rows):
    if not rows:
        return
    keys = rows[0].keys()
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--hours", type=int, default=24)
    p.add_argument(
        "--out",
        type=str,
        default=f'backups/prov-deletes-{datetime.utcnow().strftime("%Y%m%d-%H%M%S")}.json',
    )
    args = p.parse_args()

    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_PUBLIC_URL (or DATABASE_URL) must be set in environment")
        return

    conn = psycopg2.connect(db_url)
    try:
        rows = dump_rows(conn, args.hours)
        write_json(args.out, rows)
        csv_path = args.out.rsplit(".", 1)[0] + ".csv"
        write_csv(csv_path, rows)
        print(f"Wrote {len(rows)} rows to {args.out} and {csv_path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
