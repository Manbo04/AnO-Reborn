# Railway cost cut — target ≤ $30/month total

## Dashboard actions (do once, ~15 min)

### 1. Downgrade Pro → Hobby

1. Railway → **manbo04's workspace** → **Usage** or **Billing**
2. Change plan from **Pro ($20/mo)** to **Hobby ($5/mo)**
3. Hobby includes **$5** usage credit; target total bill **≤ $30**

### 2. Set RAM limits per service

Each service → **Settings** → **Resources**:

| Service | Target RAM |
|---------|------------|
| web | 512 MB (max 1 GB) |
| celery-worker | 512 MB |
| Postgres | smallest viable |
| Redis | smallest viable |

Keep **Compute Usage Limit** at **$30**.

### 3. Delete deprecated services (after deploy verified)

Once web sidecar + worker+beat are confirmed working:

1. **beat** service → Settings → **Remove service** (scheduler now runs on celery-worker)
2. **bot** service → Settings → **Remove service** (bot runs as web sidecar)

Do **not** delete Postgres or Redis.

## What the code changes do

| Change | Savings |
|--------|---------|
| `celery worker --beat` on celery-worker | Removes dedicated beat container |
| `DISCORD_BOT_SIDECAR=1` on web | Removes dedicated bot container |
| Gunicorn 2 workers × 2 threads (no preload) | Lower web RAM |
| Migrations only on worker boot | Faster, cheaper web restarts |
| Redeploy web+worker only (never Postgres) | Stops deploy-cost spikes |

## Verify after deploy

```bash
curl -s https://affairsandorder.com/ready
curl -s https://affairsandorder.com/deploy-info
```

- Discord: `/bot_version` or `/me` in your server
- Economy: resources should still tick (worker+beat schedules tasks)

## Env vars (set automatically by `railway_production_fix.py`)

| Service | Variable | Value |
|---------|----------|-------|
| web | `DISCORD_BOT_SIDECAR` | `1` |
| web | `GUNICORN_WORKERS` | `2` |
| web | `GUNICORN_THREADS` | `2` |
| celery-worker | `CELERY_CONCURRENCY` | `2` |

## Expected bill after cuts

| Item | ~Monthly |
|------|----------|
| Hobby plan | $5 |
| Postgres + Redis + 2 app services | $20–25 |
| **Total** | **$25–30** |

Monitor **Usage** for 48h; daily burn should fall from ~$2.80/day toward ~$0.85/day.
