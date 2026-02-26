#!/usr/bin/env python3
"""Restore provinces and proInfra from a backup directory created by
scripts/remove_user_provinces.py.

Usage:
  DATABASE_PUBLIC_URL=... python3 scripts/restore_provinces_backup.py --backup-dir backups/remove-provinces-33-20260209-074756 --apply

By default runs in dry-run mode and reports actions that would be taken.
"""
import argparse
import json
import os
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except Exception:
    print("psycopg2 required; pip install psycopg2-binary")
    raise


def load_backup(backup_dir):
    provinces = []
    proinfra = []
    prov_path = os.path.join(backup_dir, "provinces.json")
    pi_path = os.path.join(backup_dir, "proInfra.json")
    if os.path.exists(prov_path):
        with open(prov_path, "r", encoding="utf-8") as f:
            provinces = json.load(f)
    if os.path.exists(pi_path):
        with open(pi_path, "r", encoding="utf-8") as f:
            proinfra = json.load(f)
    return provinces, proinfra


def restore(conn, provinces, proinfra, actor="script", dry_run=True):
    with conn.cursor() as cur:
        existing_ids = set()
        cur.execute(
            "SELECT id FROM provinces WHERE id = ANY(%s)",
            ([p["id"] for p in provinces] if provinces else [None],),
        )
        for r in cur.fetchall():
            existing_ids.add(r[0])

        to_insert_provs = [p for p in provinces if p["id"] not in existing_ids]
        to_insert_pi = [pi for pi in proinfra if pi["id"] not in existing_ids]

        print(
            "Found", len(existing_ids), "existing provinces that match the backup ids"
        )
        print("Will insert provinces:", [p["id"] for p in to_insert_provs])
        print("Will insert proInfra entries:", [pi["id"] for pi in to_insert_pi])

        if dry_run:
            return {
                "dry_run": True,
                "insert_province_count": len(to_insert_provs),
                "insert_proinfra_count": len(to_insert_pi),
            }

        # Insert provinces (preserve id using explicit id insert)
        for p in to_insert_provs:
            cols = ",".join(p.keys())
            vals = ",".join(["%s"] * len(p))
            cur.execute(
                f"INSERT INTO provinces ({cols}) VALUES ({vals}) ON CONFLICT (id) DO NOTHING",
                tuple(p.values()),
            )

        for pi in to_insert_pi:
            cols = ",".join(pi.keys())
            vals = ",".join(["%s"] * len(pi))
            cur.execute(
                f"INSERT INTO proInfra ({cols}) VALUES ({vals}) ON CONFLICT (id) DO NOTHING",
                tuple(pi.values()),
            )

        # record admin action
        cur.execute(
            "INSERT INTO admin_actions (actor, action, user_id, details) VALUES (%s,%s,%s,%s)",
            (
                actor,
                "restore_provinces",
                to_insert_provs[0]["userid"] if to_insert_provs else None,
                json.dumps(
                    {
                        "restored_province_ids": [p["id"] for p in to_insert_provs],
                        "restored_proinfra_ids": [pi["id"] for pi in to_insert_pi],
                    }
                ),
            ),
        )

        return {
            "dry_run": False,
            "inserted_provinces": [p["id"] for p in to_insert_provs],
            "inserted_proinfra": [pi["id"] for pi in to_insert_pi],
        }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backup-dir", required=True)
    p.add_argument("--apply", action="store_true", default=False)
    p.add_argument("--actor", default=os.getenv("USER") or "script")
    args = p.parse_args()

    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_PUBLIC_URL (or DATABASE_URL) must be set")
        return

    provinces, proinfra = load_backup(args.backup_dir)
    if not provinces and not proinfra:
        print("No provinces/proInfra found in backup dir:", args.backup_dir)
        return

    conn = psycopg2.connect(db_url)
    try:
        if args.apply:
            result = restore(conn, provinces, proinfra, actor=args.actor, dry_run=False)
            conn.commit()
        else:
            result = restore(conn, provinces, proinfra, actor=args.actor, dry_run=True)
        print("Result:", result)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
