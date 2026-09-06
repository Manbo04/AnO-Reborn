#!/usr/bin/env python3
"""Restore tables from a backup-*.tar.gz created by app_core/backup/service.py
(nightly Celery task_backup_database, see docs/BACKUPS.md).

Manual/disaster-recovery tool only -- never invoked automatically. Defaults
to a dry run that only reports row counts; pass --apply --yes-i-am-sure to
actually truncate and reload tables.

Usage:
  # Inspect what's in a backup and how it compares to the live DB:
  DATABASE_PUBLIC_URL=... python3 scripts/restore_database_backup.py \\
      --archive backups/backup-20260906-031000.tar.gz

  # Restore everything in the archive (destructive -- truncates first):
  DATABASE_PUBLIC_URL=... python3 scripts/restore_database_backup.py \\
      --archive backups/backup-20260906-031000.tar.gz --apply --yes-i-am-sure

  # Restore only specific tables:
  ... --archive ... --tables provinces,user_military --apply --yes-i-am-sure
"""

import argparse
import csv
import json
import os
import shutil
import tarfile
import tempfile

try:
    import psycopg2
except Exception:
    print("psycopg2 required; pip install psycopg2-binary")
    raise

# Default 131072-byte field cap is too small for large text/JSON columns
# (e.g. province building/event blobs) -- raise it for the row-count pass.
csv.field_size_limit(min(2**31 - 1, __import__("sys").maxsize))


def extract_archive(archive_path: str, dest_dir: str) -> list[str]:
    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extractall(dest_dir)
    return sorted(
        name[:-4] for name in os.listdir(dest_dir) if name.endswith(".csv")
    )


def csv_row_count(path: str) -> int:
    # Use csv.reader (not a raw line count) -- quoted fields containing
    # embedded newlines (e.g. free-text columns) would otherwise inflate
    # the count and make the dry-run comparison misleading.
    with open(path, "r", encoding="utf-8", newline="") as f:
        return max(sum(1 for _ in csv.reader(f)) - 1, 0)  # minus header


def live_row_count(conn, table: str):
    try:
        with conn.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM "{table}"')
            return cur.fetchone()[0]
    except Exception as exc:
        conn.rollback()
        return f"error: {exc}"


def restore_table(conn, table: str, csv_path: str):
    with conn.cursor() as cur:
        cur.execute(f'TRUNCATE TABLE "{table}" RESTART IDENTITY CASCADE')
        with open(csv_path, "r", encoding="utf-8") as f:
            cur.copy_expert(f'COPY "{table}" FROM STDIN WITH CSV HEADER', f)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--archive", required=True, help="Path to backup-*.tar.gz")
    p.add_argument("--tables", help="Comma-separated table names (default: all tables in the archive)")
    p.add_argument("--apply", action="store_true", default=False)
    p.add_argument("--yes-i-am-sure", action="store_true", default=False,
                    help="Required alongside --apply -- this truncates live tables first")
    p.add_argument("--actor", default=os.getenv("USER") or "script")
    args = p.parse_args()

    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_PUBLIC_URL (or DATABASE_URL) must be set")
        return

    if args.apply and not args.yes_i_am_sure:
        print("--apply requires --yes-i-am-sure (this TRUNCATEs live tables before reloading them)")
        return

    stage_dir = tempfile.mkdtemp(prefix="ano-restore-")
    try:
        available = extract_archive(args.archive, stage_dir)
        selected = (
            [t.strip() for t in args.tables.split(",") if t.strip()]
            if args.tables
            else available
        )
        missing = [t for t in selected if t not in available]
        if missing:
            print(f"Not in archive: {missing}. Available: {available}")
            return

        conn = psycopg2.connect(db_url)
        try:
            print(f"Archive: {args.archive}")
            print(f"{'table':30s} {'archive_rows':>12s} {'live_rows':>12s}")
            for table in selected:
                arch_rows = csv_row_count(os.path.join(stage_dir, f"{table}.csv"))
                live_rows = live_row_count(conn, table)
                print(f"{table:30s} {arch_rows:>12} {str(live_rows):>12}")

            if not args.apply:
                print("\nDry run only -- pass --apply --yes-i-am-sure to restore.")
                return

            print(f"\nRestoring {len(selected)} table(s)...")
            for table in selected:
                restore_table(conn, table, os.path.join(stage_dir, f"{table}.csv"))
                print(f"  restored {table}")

            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "INSERT INTO admin_actions (actor, action, details) VALUES (%s,%s,%s)",
                        (
                            args.actor,
                            "restore_database_backup",
                            json.dumps({"archive": args.archive, "tables": selected}),
                        ),
                    )
            except Exception as exc:
                print(f"  (could not log to admin_actions: {exc})")

            conn.commit()
            print("Done. Committed.")
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
