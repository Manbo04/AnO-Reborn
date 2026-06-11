# Railway cost cut — target ≤ $30/month total (stay on Pro)

Pro keeps multi-region deploys so players worldwide get acceptable latency. Hobby is **not** required.

## What was leaking money (fixed 2026-06-08)

**15 extra containers** were running in stale environments:

| Environment | Services running |
|-------------|------------------|
| AnO-Reborn-pr-39, pr-46, pr-48 | web + celery-worker + Redis each |
| AnO-Reborn-pr-3, pr-52 | partial stacks |
| development | web + celery-worker + Redis |
| recovery | orphan env |

PR preview environments do **not** auto-delete when PRs close. They bill 24/7 until removed.

**Fix applied:** `python3 scripts/railway_cost_trim.py --apply` deleted all non-production environments.

## Production stack (only 4 services)

| Service | RAM cap | vCPU cap |
|---------|---------|----------|
| web | 512 MB | 1 |
| celery-worker | 512 MB | 1 |
| prod-validator (Postgres) | 1 GB | 1 |
| Redis | 512 MB | 0.5 |

Lean env vars on production:

| Service | Setting |
|---------|---------|
| web | `GUNICORN_WORKERS=1`, `GUNICORN_THREADS=2`, `DISCORD_BOT_SIDECAR=1` |
| celery-worker | `CELERY_CONCURRENCY=1`, worker runs `--beat` |

## Dashboard — do once

1. **Usage** → set **Compute Usage Limit** to **$30**
2. Confirm only **production** environment exists (no PR/dev/recovery envs)
3. Do **not** redeploy Postgres/Redis unless necessary (deploy spikes cost)

## Re-run trim script

```bash
python3 scripts/railway_cost_trim.py --dry-run   # preview
python3 scripts/railway_cost_trim.py --apply     # delete stale envs + cap prod
```

## Expected bill on Pro

| Item | ~Monthly |
|------|----------|
| Pro subscription | $20 (includes $20 usage credit) |
| Production compute (4 services, capped) | ~$8–12 |
| **Total** | **~$20–28** |

Monitor **Usage** for 48h after trim. Estimated usage should drop from ~$37 toward ~$10–15.

## Verify game still works

```bash
curl -s https://affairsandorder.com/deploy-info
curl -s https://affairsandorder.com/ready
```

Discord: `/me` in your server. Economy tasks should still tick on worker+beat.
