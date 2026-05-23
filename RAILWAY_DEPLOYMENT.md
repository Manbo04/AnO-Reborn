# Railway Deployment Guide for Affairs & Order

This guide will help you deploy the Affairs & Order game to Railway.app.

## Prerequisites

- GitHub account with AnO repository
- Railway account (sign up at https://railway.app)
- **Python runtime**: Recommended `python-3.10.x` (we test on 3.8, 3.10 and 3.14 in CI). Set `runtime.txt` to `python-3.10.19` for consistent Railway builds.
- All changes committed and pushed to your repository

## Architecture Overview

Your Railway deployment will consist of:
1. **PostgreSQL Database** - Stores all game data
2. **Redis Instance** - Message broker for Celery tasks
3. **Web Service** - Main Flask application (Gunicorn)
4. **Worker Service** - Celery worker for background tasks
5. **Beat Service** - Celery beat scheduler for periodic tasks
6. **Discord Bot Service** (optional) - Slash commands (`/register`, `/me`, etc.)

---

## Step 1: Create Railway Project

1. Go to https://railway.app and sign in with GitHub
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your `AnO` repository
5. Railway will create a new project

---

## Step 2: Add PostgreSQL Database

1. In your Railway project, click **"+ New"**
2. Select **"Database"** → **"Add PostgreSQL"**
3. Railway automatically creates a `DATABASE_URL` environment variable
4. **No additional configuration needed** - the code will parse it automatically

### Floating `postgres-volume` (must be mounted)

If the architecture graph shows **`postgres-volume` disconnected** from the **Postgres** service, the database is running on the wrong disk (often a new empty volume). Game data will look frozen (no `user_economy` updates).

**Postgres must have exactly one volume at:**

```text
/var/lib/postgresql/data
```

**Dashboard (recommended):**

1. Open the **Postgres** service (not web/celery).
2. Go to **Settings** → **Volumes** (or click the volume on the canvas).
3. If a volume like `postgres-2026-05-08-...` is attached but `postgres-volume` is floating:
   - **Detach** the empty/wrong volume from Postgres (only if you confirmed it has no player data).
   - Click the floating **`postgres-volume`** → **Connect to service** → choose **Postgres**.
   - Set mount path: `/var/lib/postgresql/data`.
4. **Deploy** Postgres first, wait until healthy.
5. Redeploy **beat**, **celery-worker**, and **web**.

**CLI (after `railway login` && `railway link`):**

```bash
railway volume list
railway volume list --service Postgres
./scripts/railway_mount_postgres_volume.sh --dry-run
./scripts/railway_mount_postgres_volume.sh
```

**Verify after mount:**

```bash
DATABASE_PUBLIC_URL=... python3 scripts/progression_health_check.py
```

`user_economy.updated_at` should advance within ~75 minutes once Celery runs.

**Do not** attach two volumes to the same mount path on Postgres.

---

## Step 3: Add Redis

1. Click **"+ New"** again
2. Select **"Database"** → **"Add Redis"**
3. Railway automatically creates a `REDIS_URL` environment variable
4. **No additional configuration needed** - the code will parse it automatically

---

## Step 4: Configure Web Service (Main App)

1. Click on your main service (the one connected to GitHub)
2. Go to **"Settings"** tab
3. Set the **Start Command**:
   ```
   gunicorn wsgi:app --workers 4 --threads 2 --worker-class gthread --timeout 120 --bind 0.0.0.0:$PORT --access-logfile - --error-logfile - --log-level info --keep-alive 30 --max-requests 1000 --max-requests-jitter 100
   ```
4. Add **Environment Variables** (Settings → Variables):
   ```
   ENVIRONMENT=PROD
   SECRET_KEY=<generate-a-long-random-string>
   DISCORD_WEBHOOK_URL=<your-discord-webhook-url>
   SENDGRID_API_KEY=<your-sendgrid-api-key>
   ```

> Tip: Set the **Health Check / Readiness Path** in Railway to `/ready` (this endpoint validates DB connectivity).

   To generate a secure SECRET_KEY, run in terminal:
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```

5. Under **"Networking"**, enable **Public Networking** and note your URL

---

## Step 5: Create Celery Worker Service

1. Click **"+ New"** → **"GitHub Repo"**
2. Select the **same AnO repository**
3. Railway will create a new service
4. Go to **"Settings"** tab
5. Set **Service Name**: `celery-worker`
6. Set **Start Command**:
   ```
   celery -A tasks.celery worker --loglevel=INFO
   ```
7. Under **"Variables"**, add the same environment variables:
   ```
   ENVIRONMENT=PROD
   SECRET_KEY=<same-as-web-service>
   DISCORD_WEBHOOK_URL=<your-discord-webhook-url>
   SENDGRID_API_KEY=<your-sendgrid-api-key>
   ```
8. **Important**: Link to the same PostgreSQL and Redis instances:
   - Click **"Variables"** → **"Reference Variables"**
   - Add references from the PostgreSQL and Redis services

---

## Step 6: Discord bot (existing `bot` service)

If you already have a Railway service named **`bot`** (invited to Discord, `DISCORD_BOT_TOKEN` set), reconfigure it for Phase 1:

### Start command (required)

Replace any HTTP server / `PORT=5005` setup. The bot is a **Discord gateway client**, not a web app:

```
python scripts/run_discord_bot_if_leader.py
```

Remove obsolete variables: `DISCORD_BOT_URL`, `PORT` (not used by this codebase).

### Variables on the `bot` service (easy mode — recommended)

Your `bot` service is already wired to **Postgres** on the canvas. You only need:

| Variable | How to set |
|----------|------------|
| `DISCORD_BOT_TOKEN` | Already set |
| `DATABASE_URL` | **+ Variable → Reference → Postgres → `DATABASE_URL`** |

Optional: `REDIS_URL` (reference from Redis) for leader lock if you run multiple bot replicas.

You do **not** need `SECRET_KEY`, `BOT_API_BASE_URL`, `DISCORD_BOT_URL`, or `PORT` on the bot when using the database (default after latest deploy).

### Alternative: HTTP API mode (no Postgres on bot)

| Variable | Value |
|----------|--------|
| `DISCORD_BOT_TOKEN` | Your bot token |
| `BOT_API_BASE_URL` | `https://affairsandorder.com` |
| `SECRET_KEY` | Reference from **web** service |
| `REDIS_URL` | Reference from Redis |

### Web service

`SECRET_KEY` is enough for the bot API (`/api/bot/*`) — auth is derived automatically until you set `BOT_API_SECRET`.

### After deploy

Check **bot → Logs** for:

- `data mode=database`
- `embed_ui=2.1` (or newer — confirms nation embed redesign is loaded)
- `Synced N global slash command(s)` with **N ≥ 13** (includes `/bot_version`)

### Bot embeds still look old?

If `/nation` shows field names like **Influence (score)** and **Resources (top holdings)**, the running container is **not** on current `master` — that layout was removed in commit `5d28c8dc`.

1. Run `/bot_version` — embed UI should be **2.1+**. If the command is missing or UI version is old, redeploy.
2. Railway → **bot** service → **Deployments** → confirm latest commit is recent `master`.
3. **Settings → Build**: `Dockerfile.discord-bot` (or config file `railway.discord-bot.json`), **not** the web Nixpacks/gunicorn image.
4. **Redeploy** manually (⋯ → Redeploy). GitHub Actions workflow **Redeploy Discord Bot** only calls Railway API when `RAILWAY_TOKEN` is set; otherwise it exits without redeploying.
5. After deploy, check logs for `embed_ui=2.1` and run `/nation` again (embeds are not cached).

Tables are created automatically on web boot. One-time migration (optional):

```bash
python3 scripts/apply_discord_bot_migration.py
```

### Player flow

**Account → Generate Bot Link Code** → Discord `/register code:XXXXXXXX` → `/me`, `/wars`, `/resources`, `/nation`

Slash commands can take up to ~1 hour to appear globally on first deploy; re-invite is not required if the bot is already in your server.

---

## Step 7: Create Celery Beat Service

1. Click **"+ New"** → **"GitHub Repo"**
2. Select the **same AnO repository** again
3. Go to **"Settings"** tab
4. Set **Service Name**: `celery-beat`
5. Set **Start Command**:
   ```
   celery -A tasks.celery beat --loglevel=INFO
   ```
6. Add the same environment variables as worker
7. Link to the same PostgreSQL and Redis instances

---

## Step 8: Apply Changes and Deploy

1. In the Railway dashboard, you should see **"Apply 2 changes"** (or similar)
2. Click **"Details"** to review changes
3. Click **"Deploy"** or **"Apply changes"**
4. Wait for all services to build and deploy (this may take 5-10 minutes)

---

## Step 9: Initialize Database (First Deployment Only)

After the first successful deployment:

1. Click on the **Web Service**
2. Go to **"Deployments"** tab
3. Click on the latest deployment
4. You may need to run database initialization scripts

Option A: Use Railway CLI (if you have it installed):
```bash
railway run python affo/create_db.py
```

Option B: Add a one-time initialization task to your code

---

## Monitoring & Logs

### View Logs
- Click on any service (Web, Worker, Beat)
- Go to **"Logs"** tab
- Monitor for errors or issues

### Common Issues & Solutions

**Problem**: "Failed to connect to database"
- **Solution**: Check that PostgreSQL service is running and DATABASE_URL is available

**Problem**: "Failed to connect to Redis"
- **Solution**: Check that Redis service is running and REDIS_URL is available

**Problem**: "Worker not processing tasks"
- **Solution**: Ensure Worker and Beat services are both running and connected to Redis

**Problem**: "Application Error" or 500 errors
- **Solution**: Check web service logs for Python errors, ensure all environment variables are set

---

## Environment Variables Summary

### Required for ALL services:
- `DATABASE_URL` - Automatically provided by Railway PostgreSQL
- `REDIS_URL` - Automatically provided by Railway Redis
- `ENVIRONMENT` - Set to `PROD`
- `SECRET_KEY` - Generate a secure random string

### Optional (but recommended):
- `DISCORD_WEBHOOK_URL` - For error notifications
- `SENDGRID_API_KEY` - For email functionality

### Legacy variables (now auto-parsed from DATABASE_URL):
These are automatically set by the `config.py` module:
- `PG_HOST`
- `PG_PORT`
- `PG_USER`
- `PG_PASSWORD`
- `PG_DATABASE`

---

## Cost Estimates

Railway pricing (as of 2024):
- **Free Trial**: $5 credit (good for testing)
- **Hobby Plan**: $5/month + usage
- **Typical monthly cost**: $10-25/month depending on traffic

Resource usage:
- PostgreSQL: ~$2-5/month
- Redis: ~$2-3/month
- Web Service: ~$3-10/month
- Worker + Beat: ~$3-7/month

---

## Scaling & Performance

### Scale Web Service:
1. Go to Web Service → Settings
2. Adjust **Workers** in start command (currently 4)
3. Monitor RAM usage and adjust as needed

### Scale Worker Service:
1. Create additional worker services if needed
2. All workers will share the same Redis queue

### Database Optimization:
- Monitor query performance in logs
- Consider upgrading PostgreSQL plan if needed
- The new `database.py` module includes connection pooling for better performance

---

## Support & Troubleshooting

### Railway Dashboard
- View all services: https://railway.app/dashboard
- Check service health and resource usage

### Common Commands (if using Railway CLI)
```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Link to project
railway link

# View logs
railway logs

# Run commands in production
railway run python manage.py migrate
```

---

## Updating Your Deployment

When you push changes to GitHub:
1. Railway automatically detects the push
2. Services rebuild and redeploy
3. Zero-downtime deployment (if configured)

To deploy manually:
1. Go to service in Railway dashboard
2. Click **"Deploy"** → **"Trigger Deploy"**

---

## Next Steps After Deployment

1. ✅ Test the game at your Railway URL
2. ✅ Configure custom domain (optional)
3. ✅ Set up monitoring/alerts
4. ✅ Test Celery tasks are running (check logs)
5. ✅ Verify database is accessible
6. ✅ Test user registration and login

---

## Notes

- The `config.py` module automatically parses Railway's `DATABASE_URL` and `REDIS_URL` into the format your application expects
- Connection pooling is enabled via `database.py` for better performance
- All services share the same database and Redis instances
- Logs are available in real-time in the Railway dashboard

## Questions?

Check Railway documentation: https://docs.railway.app
