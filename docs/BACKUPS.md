# Database backups

Automated since 2026-09-06. Protects against bad migrations, accidental
deletes, and application bugs that corrupt data -- it does not replace
Railway/Postgres-level replication and is not a defense against losing the
whole Railway account.

## How it works

- `tasks.task_backup_database` runs nightly at 03:10 UTC via Celery beat on
  the `celery-worker` service (schedule: `BACKUP_CRON` env var, crontab
  minute-of-hour format, default `10 3`).
- `app_core/backup/service.py` connects directly with psycopg2 (no `pg_dump`
  binary is installed in the app image) and `COPY`s every `public` base
  table to CSV, then packs them into one `backup-YYYYMMDD-HHMMSS.tar.gz`.
- Archives are written to `/data/backups`, which is `celery-worker-volume`
  -- a 50GB Railway volume attached to the `celery-worker` service, separate
  from the Postgres data volume. `BACKUP_DIR` env var overrides the path.
- Archives older than `BACKUP_RETENTION_DAYS` (default 30) are pruned after
  each run.
- Guarded by `@leader_only`, same as every other beat task, so it only runs
  once even with multiple worker replicas.

## Restoring

`scripts/restore_database_backup.py` -- manual only, never scheduled.
Defaults to a dry run (row-count comparison, no writes). Restoring
truncates the target table(s) before reloading, so it requires both
`--apply` and `--yes-i-am-sure`:

```
# Inspect an archive against the live DB, no changes made:
DATABASE_PUBLIC_URL=... python3 scripts/restore_database_backup.py \
    --archive backups/backup-20260906-031000.tar.gz

# Restore everything in the archive:
DATABASE_PUBLIC_URL=... python3 scripts/restore_database_backup.py \
    --archive backups/backup-20260906-031000.tar.gz --apply --yes-i-am-sure

# Restore only specific tables:
... --tables provinces,user_military --apply --yes-i-am-sure
```

Each apply is logged to `admin_actions` (action=`restore_database_backup`).

To pull an archive off the Railway volume: `railway ssh -s celery-worker`
then copy out of `/data/backups`, or use `railway run` with a one-off
command that streams the file.

## Known limitations / possible follow-ups

- Backups live only on Railway (same platform as the live DB). They protect
  against bad migrations/accidental deletes/app bugs, not against losing
  the Railway account itself. Pushing a copy to an off-platform
  S3-compatible bucket (Cloudflare R2 / Backblaze B2, both have free tiers)
  would close that gap -- not implemented yet, no credentials configured.
- Data-only: CSV dumps, not schema. A full restore assumes the schema
  already exists (recreate it via `scripts/apply_all_pending_migrations.py`
  against a fresh database first, then reload data).
- No automated restore-verification job (e.g. periodically restoring into
  a scratch DB to confirm archives are actually valid).
