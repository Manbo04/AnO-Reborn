"""Full-database backup for disaster recovery (bad migrations, accidental
deletes, corruption) -- not a substitute for point-in-time replication.

Dumps every public table to CSV via psycopg2 COPY (no pg_dump binary is
installed in the app image, and this mirrors the approach already proven
to work here in scripts/backup_tables_direct.py), packs them into one
timestamped .tar.gz on the celery-worker's persistent volume, and prunes
archives past the retention window.

Restore with scripts/restore_database_backup.py (manual, never automated).
"""
from __future__ import annotations

import os
import shutil
import tarfile
import tempfile
import time

import psycopg2

import config  # noqa: F401  (populates PG_* env vars from DATABASE_URL)

BACKUP_DIR = os.getenv("BACKUP_DIR", "/data/backups")
RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
IGNORED_TABLES = {"schema_migrations"}


def _connect():
    return psycopg2.connect(
        dbname=os.getenv("PG_DATABASE"),
        user=os.getenv("PG_USER"),
        password=os.getenv("PG_PASSWORD"),
        host=os.getenv("PG_HOST", "localhost"),
        port=int(os.getenv("PG_PORT", "5432")),
    )


def _dump_tables_to_dir(conn, out_dir: str) -> list[str]:
    dumped = []
    with conn.cursor() as cur:
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' "
            "ORDER BY table_name"
        )
        tables = [r[0] for r in cur.fetchall() if r[0] not in IGNORED_TABLES]

        for table in tables:
            out_path = os.path.join(out_dir, f"{table}.csv")
            with open(out_path, "w", encoding="utf-8") as f:
                cur.copy_expert(f'COPY "{table}" TO STDOUT WITH CSV HEADER', f)
            dumped.append(table)
    return dumped


def run_backup() -> dict:
    """Dump every public table and archive it under BACKUP_DIR. Returns a
    summary dict; raises on failure (caller decides how to log/alert)."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    archive_name = f"backup-{ts}.tar.gz"
    archive_path = os.path.join(BACKUP_DIR, archive_name)

    started = time.time()
    stage_dir = tempfile.mkdtemp(prefix="ano-backup-")
    try:
        conn = _connect()
        try:
            tables = _dump_tables_to_dir(conn, stage_dir)
        finally:
            conn.close()

        with tarfile.open(archive_path, "w:gz") as tar:
            for table in tables:
                tar.add(os.path.join(stage_dir, f"{table}.csv"), arcname=f"{table}.csv")
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    elapsed = time.time() - started
    size_bytes = os.path.getsize(archive_path)
    return {
        "archive_path": archive_path,
        "table_count": len(tables),
        "size_bytes": size_bytes,
        "elapsed_seconds": round(elapsed, 1),
    }


def prune_old_backups() -> list[str]:
    """Delete archives in BACKUP_DIR older than RETENTION_DAYS. Returns the
    list of deleted filenames."""
    if not os.path.isdir(BACKUP_DIR):
        return []

    cutoff = time.time() - RETENTION_DAYS * 86400
    deleted = []
    for name in os.listdir(BACKUP_DIR):
        if not (name.startswith("backup-") and name.endswith(".tar.gz")):
            continue
        path = os.path.join(BACKUP_DIR, name)
        try:
            if os.path.getmtime(path) < cutoff:
                os.remove(path)
                deleted.append(name)
        except OSError:
            continue
    return deleted
