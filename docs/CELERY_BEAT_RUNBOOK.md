# Celery beat and economy task runbook

## Symptoms

- Resources or tax income frozen for all players
- `/ready` returns `generate_province_revenue: stale`
- `progression_health_check.py` reports P0 stale `task_runs`

## Checks

```bash
DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
DATABASE_PUBLIC_URL=... python3 scripts/diagnose_schema.py
```

In Railway logs, search for:

- `Did not acquire beat leader lock`
- `celery beat exited`
- `generate_province_revenue: skipped`

## Recovery

1. Redeploy or restart the **beat** service (not only web).
2. If tasks remain stale, call `/_admin/trigger_tasks` with header `X-DIAG-SECRET: $ADMIN_DIAG_SECRET`.
3. Verify `task_runs` rows update within 90 minutes.

## Prevention

- Beat uses `scripts/run_beat_if_leader.py` with lock retry and `sys.exit(1)` on failure so Railway restarts the process.
- Web boot runs `apply_all_pending_migrations.py` before Gunicorn.
