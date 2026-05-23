#!/usr/bin/env python3
"""One-shot Railway production repair: bot Online + Discord embed UI from web.

Requires:
  export RAILWAY_TOKEN='...'

Run:
  python3 scripts/railway_production_fix.py

Postgres volume attachment must be fixed in the dashboard if Postgres is Crashed
(see docs/RAILWAY_FIX_ONCE.md).
"""

from __future__ import annotations

import os
import secrets
import sys

# Import helpers from sibling script (same directory on path).
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import railway_discord_bot_setup as rds  # noqa: E402

POSTGRES_VOLUME_HELP = r"""
POSTGRES CRASHED — fix in Railway UI first:
  1. Postgres service → Settings → Volumes
  2. Exactly ONE volume at /var/lib/postgresql/data
  3. Detach empty/wrong volumes (e.g. postgres-2026-05-08-*)
  4. Attach postgres-volume to Postgres at that path
  5. Deploy Postgres → wait Online
  6. Re-run this script
"""


def _service_id(services: list, *names: str) -> str | None:
    by_name = {s["name"].lower(): s["id"] for s in services}
    for name in names:
        sid = by_name.get(name.lower())
        if sid:
            return sid
    for s in services:
        for name in names:
            if name.lower() in s["name"].lower():
                return s["id"]
    return None


def _configure_all(
    token: str, project_id: str, env_id: str, services: list, base_url: str
) -> None:
    web_id = _service_id(services, "web")
    bot_id = _service_id(services, "bot", rds.BOT_SERVICE_NAME)
    if not web_id or not bot_id:
        raise RuntimeError("web and bot services required in project")

    web_vars = rds._get_service_variables(token, project_id, env_id, web_id)
    bot_secret = os.getenv("BOT_API_SECRET", "").strip() or secrets.token_hex(32)

    rds._upsert_var(token, project_id, env_id, web_id, "BOT_API_SECRET", bot_secret)
    rds._upsert_var(token, project_id, env_id, web_id, "BOT_API_BASE_URL", base_url)
    rds._upsert_var(token, project_id, env_id, web_id, "DISCORD_BOT_SIDECAR", "0")

    for obsolete in ("DISCORD_BOT_URL", "PORT"):
        rds._delete_var(token, project_id, env_id, bot_id, obsolete)

    rds._upsert_var(
        token, project_id, env_id, bot_id, "RAILWAY_DOCKERFILE_PATH", "Dockerfile.discord-bot"
    )
    rds._upsert_var(token, project_id, env_id, bot_id, "DISCORD_BOT_USE_WEB_EMBEDS", "1")
    rds._upsert_var(token, project_id, env_id, bot_id, "DISCORD_BOT_SKIP_LEADER_LOCK", "1")
    rds._upsert_var(
        token, project_id, env_id, bot_id, "DISCORD_BOT_LEADER_LOCK_KEY", "discord_bot:leader:v3"
    )
    rds._upsert_var(token, project_id, env_id, bot_id, "BOT_API_BASE_URL", base_url)
    rds._upsert_var(token, project_id, env_id, bot_id, "BOT_API_SECRET", bot_secret)

    db_url = web_vars.get("DATABASE_PUBLIC_URL") or web_vars.get("DATABASE_URL")
    if db_url:
        rds._upsert_var(token, project_id, env_id, bot_id, "DATABASE_URL", db_url)
    redis_url = web_vars.get("REDIS_URL")
    if redis_url:
        rds._upsert_var(token, project_id, env_id, bot_id, "REDIS_URL", redis_url)
    secret = web_vars.get("SECRET_KEY")
    if secret:
        rds._upsert_var(token, project_id, env_id, bot_id, "SECRET_KEY", secret)

    rds._set_start_command(token, bot_id, env_id, rds.BOT_START_COMMAND)
    print("Bot configured: web embeds, skip leader lock, Dockerfile.discord-bot")


def _redeploy_chain(token: str, env_id: str, services: list) -> None:
    for name in ("Postgres", "postgres", "web", "beat", "celery-worker", "bot"):
        sid = _service_id(services, name)
        if not sid:
            continue
        label = next((s["name"] for s in services if s["id"] == sid), name)
        try:
            rds._redeploy(token, sid, env_id)
            print(f"  redeploy: {label}")
        except Exception as exc:
            print(f"  WARN {label}: {exc}")


def main() -> None:
    token = os.getenv("RAILWAY_TOKEN", "").strip()
    if not token:
        print("ERROR: export RAILWAY_TOKEN=...")
        print(POSTGRES_VOLUME_HELP)
        print("See docs/RAILWAY_FIX_ONCE.md")
        sys.exit(1)

    project_id = os.getenv("RAILWAY_PROJECT_ID", rds.DEFAULT_PROJECT_ID)
    base_url = os.getenv("BOT_API_BASE_URL", "https://affairsandorder.com").rstrip("/")

    envs = rds._project_environments(token, project_id)
    env_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip()
    if not env_id:
        for env in envs:
            if env.get("name", "").lower() == "production":
                env_id = env["id"]
                break
        if not env_id and envs:
            env_id = envs[0]["id"]

    services = rds._project_services(token, project_id)
    print("Services:", ", ".join(s["name"] for s in services))
    print(POSTGRES_VOLUME_HELP)

    print("\nConfiguring variables...")
    _configure_all(token, project_id, env_id, services, base_url)

    print("\nRedeploying (Postgres first)...")
    _redeploy_chain(token, env_id, services)

    print("\nAfter deploy (~10 min):")
    print("  curl -s https://affairsandorder.com/api/bot/embed_version")
    print("  Discord: /bot_version  then  /nation")


if __name__ == "__main__":
    main()
