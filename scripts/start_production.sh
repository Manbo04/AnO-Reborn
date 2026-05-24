#!/usr/bin/env bash
# Web service entry: optional Discord bot sidecar + gunicorn.
# Pushes to master redeploy the web service; the sidecar runs latest bot code and
# renders embeds via the web API (DISCORD_BOT_USE_WEB_EMBEDS=1).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${PORT:-8080}"

# Dedicated Railway "bot" service should run the bot. Web sidecar is opt-in only.
if [[ -n "${DISCORD_BOT_TOKEN:-}" && "${DISCORD_BOT_SIDECAR:-0}" == "1" ]]; then
  echo "[start] Discord bot sidecar: clearing stale leader locks..."
  python3 - <<'PY' || true
import os
import urllib.parse
url = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
if not url:
    raise SystemExit(0)
import redis
p = urllib.parse.urlparse(url)
r = redis.Redis(host=p.hostname, port=p.port or 6379, password=p.password)
for key in ("discord_bot:leader", "discord_bot:leader:v2", "discord_bot:leader:v3"):
    r.delete(key)
print("  cleared leader lock keys")
PY
  export DISCORD_BOT_USE_WEB_EMBEDS=1
  export DISCORD_BOT_LEADER_LOCK_KEY="discord_bot:leader:v3"
  export BOT_API_BASE_URL="${BOT_API_BASE_URL:-https://affairsandorder.com}"
  echo "[start] Starting Discord bot sidecar (embeds from web API)..."
  python3 scripts/run_discord_bot_if_leader.py >>/tmp/discord-bot.log 2>&1 &
else
  echo "[start] DISCORD_BOT_TOKEN unset — skip Discord sidecar."
  echo "[start] Add DISCORD_BOT_TOKEN to the web service (or use a dedicated bot service)."
fi

if [[ -n "${DATABASE_PUBLIC_URL:-}${DATABASE_URL:-}" ]]; then
  echo "[start] Applying pending SQL migrations (best-effort)..."
  python3 scripts/apply_all_pending_migrations.py || echo "[start] WARN: migrations script exited non-zero"
  echo "[start] Next.js compatibility views (best-effort)..."
  python3 scripts/apply_nextjs_compat_views.py || echo "[start] WARN: compat views script exited non-zero"
else
  echo "[start] No DATABASE_URL — skip migrations"
fi

echo "[start] Starting gunicorn on :${PORT}..."
exec gunicorn \
  --bind "0.0.0.0:${PORT}" \
  --preload \
  --workers 4 \
  --threads 4 \
  --worker-class gthread \
  --timeout 120 \
  --graceful-timeout 15 \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --keep-alive 30 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  wsgi:app
