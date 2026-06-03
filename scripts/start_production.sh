#!/usr/bin/env bash
# Web service entry: optional Discord bot sidecar + gunicorn.
# Pushes to master redeploy the web service; the sidecar runs latest bot code and
# renders embeds via the web API (DISCORD_BOT_USE_WEB_EMBEDS=1).
set -euo pipefail
cd "$(dirname "$0")/.."

export ANO_USE_START_SCRIPT=1
export ANO_BOOT_MARKER="${RAILWAY_GIT_COMMIT_SHA:-unknown}"

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
  python3 -c "
from database import ensure_schema_compat, schema_compat_succeeded, schema_compat_failed_steps
ensure_schema_compat()
ok = schema_compat_succeeded()
print('[start] schema_compat', 'ok' if ok else 'failed', schema_compat_failed_steps()[:5])
" || echo "[start] WARN: schema compat check failed"
  echo "[start] Nudge stale economy tasks if beat missed schedules..."
  python3 scripts/nudge_stale_economy_tasks.py || echo "[start] WARN: economy nudge exited non-zero"
else
  echo "[start] No DATABASE_URL — skip migrations"
fi

export ANO_BOOT_DONE=1

SERVICE_NAME="${RAILWAY_SERVICE_NAME:-web}"

if [[ "$SERVICE_NAME" == *"worker"* ]] || [[ "$SERVICE_NAME" == *"celery"* ]]; then
  echo "[start] Starting Celery worker for service $SERVICE_NAME..."
  exec celery -A tasks worker --loglevel=INFO
elif [[ "$SERVICE_NAME" == *"beat"* ]]; then
  echo "[start] Starting Celery beat for service $SERVICE_NAME..."
  exec python3 scripts/run_beat_if_leader.py
elif [[ "$SERVICE_NAME" == *"bot"* ]] || [[ "$SERVICE_NAME" == *"discord"* ]]; then
  echo "[start] Starting Discord bot for service $SERVICE_NAME..."
  exec python3 scripts/run_discord_bot_if_leader.py
else
  echo "[start] Starting gunicorn on :${PORT} for service $SERVICE_NAME..."
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
fi
