#!/usr/bin/env bash
# Web service entry: optional Discord bot sidecar + gunicorn.
# Cost-optimized: bot sidecar on web, celery worker+beat merged, slim gunicorn.
set -euo pipefail
cd "$(dirname "$0")/.."

export ANO_USE_START_SCRIPT=1
export ANO_BOOT_MARKER="${RAILWAY_GIT_COMMIT_SHA:-unknown}"

PORT="${PORT:-8080}"
SERVICE_NAME="${RAILWAY_SERVICE_NAME:-web}"

# Discord bot sidecar on web (replaces dedicated bot service — saves one container).
if [[ -n "${DISCORD_BOT_TOKEN:-}" && "${DISCORD_BOT_SIDECAR:-1}" == "1" ]]; then
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
  echo "[start] Discord bot sidecar disabled (DISCORD_BOT_SIDECAR=${DISCORD_BOT_SIDECAR:-0})."
fi

# Heavy boot (migrations, schema compat, economy nudge) runs on celery-worker only.
# Web starts gunicorn fast; worker owns DB schema + Celery beat schedule.
_is_worker_service() {
  [[ "$SERVICE_NAME" == *"worker"* || "$SERVICE_NAME" == *"celery"* ]]
}

if [[ -n "${DATABASE_PUBLIC_URL:-}${DATABASE_URL:-}" ]] && _is_worker_service; then
  echo "[start] Worker boot: applying migrations and schema compat..."
  python3 scripts/apply_all_pending_migrations.py || echo "[start] WARN: migrations script exited non-zero"
  python3 patch_wars.py || echo "[start] WARN: patch_wars exited non-zero"
  python3 scripts/patch_interactive_events.py || echo "[start] WARN: patch_interactive_events exited non-zero"
  python3 scripts/apply_nextjs_compat_views.py || echo "[start] WARN: compat views script exited non-zero"
  python3 -c "
from database import ensure_schema_compat, schema_compat_succeeded, schema_compat_failed_steps
ensure_schema_compat()
ok = schema_compat_succeeded()
print('[start] schema_compat', 'ok' if ok else 'failed', schema_compat_failed_steps()[:5])
" || echo "[start] WARN: schema compat check failed"
  echo "[start] Nudge stale economy tasks if beat missed schedules..."
  python3 scripts/nudge_stale_economy_tasks.py || echo "[start] WARN: economy nudge exited non-zero"
elif [[ -n "${DATABASE_PUBLIC_URL:-}${DATABASE_URL:-}" ]]; then
  echo "[start] Running migrations on $SERVICE_NAME to guarantee execution..."
  python3 scripts/apply_all_pending_migrations.py || echo "[start] WARN: migrations script exited non-zero"
  python3 patch_wars.py || echo "[start] WARN: patch_wars exited non-zero"
  python3 scripts/patch_interactive_events.py || echo "[start] WARN: patch_interactive_events exited non-zero"
  python3 -c "
from database import ensure_schema_compat, schema_compat_succeeded
ensure_schema_compat()
print('[start] web schema_compat', 'ok' if schema_compat_succeeded() else 'failed')
" || echo "[start] WARN: web schema_compat check failed"
else
  echo "[start] No DATABASE_URL — skip migrations"
fi

export ANO_BOOT_DONE=1

if _is_worker_service; then
  CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-1}"
  echo "[start] Starting Celery worker+beat (concurrency=${CELERY_CONCURRENCY})..."
  exec celery -A tasks worker --beat --loglevel=INFO --concurrency="${CELERY_CONCURRENCY}"
elif [[ "$SERVICE_NAME" == *"beat"* ]]; then
  echo "[start] WARN: dedicated beat service is deprecated — use celery-worker with --beat."
  exec python3 scripts/run_beat_if_leader.py
elif [[ "$SERVICE_NAME" == *"bot"* ]] || [[ "$SERVICE_NAME" == *"discord"* ]]; then
  echo "[start] WARN: dedicated bot service is deprecated — use DISCORD_BOT_SIDECAR=1 on web."
  exec python3 scripts/run_discord_bot_if_leader.py
else
  GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
  GUNICORN_THREADS="${GUNICORN_THREADS:-2}"
  echo "[start] Starting gunicorn on :${PORT} (workers=${GUNICORN_WORKERS} threads=${GUNICORN_THREADS})..."
  exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${GUNICORN_WORKERS}" \
    --threads "${GUNICORN_THREADS}" \
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
