# Fix production once (natural-gratitude / Affairs & Order)

Use this when Railway shows **Postgres Crashed**, **bot Completed**, Discord UI old, or `/nation` hangs.

---

## Root cause (your screenshot)

1. **Postgres crashed** — nothing can load game data until this is **Online**.
2. **Wrong volume** — `postgres-2026-05-08-...` attached instead of **`postgres-volume`** is the usual reason.
3. **bot Completed** — bot process exited; Discord still talks to old code.

---

## Step A — Fix Postgres (dashboard, ~3 min)

1. Open Railway → **Postgres** (red / Crashed).
2. **Settings** → **Volumes**.
3. You must have **only one** volume mounted at:

   `/var/lib/postgresql/data`

4. If you see **`postgres-2026-05-08-...`** on Postgres:
   - Detach it **only if** you confirmed it is empty / not your live data.
5. Attach **`postgres-volume`** to **Postgres** at `/var/lib/postgresql/data`.
6. **Do not** attach Postgres data volumes to **bot** or **web** — only the Postgres service.
7. Click **Deploy** on Postgres → wait until status is **Online** (not Crashed, not Deploying).

Verify:

```bash
curl -s https://affairsandorder.com/health
# ok
```

---

## Step B — Fix bot (dashboard or script)

### Option 1 — Automated (recommended)

GitHub → repo **Secrets** → add **`RAILWAY_TOKEN`** (Railway account token).

Locally or in Actions:

```bash
export RAILWAY_TOKEN='your-token'
python3 scripts/railway_production_fix.py
```

### Option 2 — Manual variables on **bot** service

| Variable | Value |
|----------|--------|
| `DISCORD_BOT_TOKEN` | (your bot token) |
| `DISCORD_BOT_USE_WEB_EMBEDS` | `1` |
| `DISCORD_BOT_SKIP_LEADER_LOCK` | `1` |
| `BOT_API_BASE_URL` | `https://affairsandorder.com` |
| `SECRET_KEY` | Reference → **web** |
| `DATABASE_URL` | Reference → **Postgres** |
| `REDIS_URL` | Reference → **Redis** |
| `RAILWAY_DOCKERFILE_PATH` | `Dockerfile.discord-bot` |

**Settings:**

- Start command: `python scripts/run_discord_bot_if_leader.py`
- Restart policy: **Always**

On **web** service set:

| Variable | Value |
|----------|--------|
| `DISCORD_BOT_SIDECAR` | `0` |

(Do not run a second bot on web.)

**Redeploy** `bot` → must show **Online**, not **Completed**.

---

## Step C — Verify Discord UI

1. `curl -s https://affairsandorder.com/api/bot/embed_version`  
   → `{"embed_ui":"2.1","ok":true}`

2. Discord `/bot_version` → Embed UI **2.1**, mode **web-embeds**

3. `/nation` → title **🏛️ Nation name**, **💰 Treasury**, footer `embed UI 2.1`

---

## If bot stays "Completed"

Open **bot** → latest deployment → **Logs**. Look for:

- `DISCORD_BOT_TOKEN not set` → add token on bot service
- `Leader lock` → ensure `DISCORD_BOT_SKIP_LEADER_LOCK=1`
- Import / DB errors → fix Postgres first

---

## Order of operations

```text
Postgres Online → redeploy web → redeploy bot → test Discord
```

Never test `/nation` while Postgres is Crashed or Deploying.
