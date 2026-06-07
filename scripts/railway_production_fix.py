#!/usr/bin/env python3
"""One-shot Railway production repair: web sidecar bot + scoped redeploys.

Requires:
  export RAILWAY_TOKEN='...'

Run:
  python3 scripts/railway_production_fix.py
  python3 scripts/railway_production_fix.py --redeploy-only --services web,celery-worker

Postgres volume attachment must be fixed in the dashboard if Postgres is Crashed
(see docs/RAILWAY_FIX_ONCE.md).
"""


import os
import secrets
import sys

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

# Never auto-redeploy databases on code push — wastes compute and risks downtime.
DEFAULT_REDEPLOY_SERVICES = ("web", "celery-worker")


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


def _configure_sidecar_web(
    token: str, project_id: str, env_id: str, services: list, base_url: str
) -> None:
    web_id = _service_id(services, "web")
    if not web_id:
        raise RuntimeError("web service required in project")

    bot_id = _service_id(services, "bot", rds.BOT_SERVICE_NAME)
    web_vars = rds._get_service_variables(token, project_id, env_id, web_id)
    bot_secret = os.getenv("BOT_API_SECRET", "").strip() or secrets.token_hex(32)

    rds._upsert_var(token, project_id, env_id, web_id, "BOT_API_SECRET", bot_secret)
    rds._upsert_var(token, project_id, env_id, web_id, "BOT_API_BASE_URL", base_url)
    rds._upsert_var(token, project_id, env_id, web_id, "DISCORD_BOT_SIDECAR", "1")
    rds._upsert_var(token, project_id, env_id, web_id, "DISCORD_BOT_USE_WEB_EMBEDS", "1")
    rds._upsert_var(token, project_id, env_id, web_id, "GUNICORN_WORKERS", "2")
    rds._upsert_var(token, project_id, env_id, web_id, "GUNICORN_THREADS", "2")

    worker_id = _service_id(services, "celery-worker")
    if worker_id:
        rds._upsert_var(token, project_id, env_id, worker_id, "CELERY_CONCURRENCY", "2")

    if bot_id:
        bot_vars = rds._get_service_variables(token, project_id, env_id, bot_id)
        bot_token = (bot_vars.get("DISCORD_BOT_TOKEN") or "").strip()
        if bot_token:
            rds._upsert_var(
                token, project_id, env_id, web_id, "DISCORD_BOT_TOKEN", bot_token
            )
            print("  copied DISCORD_BOT_TOKEN from bot → web (sidecar)")
        elif not (web_vars.get("DISCORD_BOT_TOKEN") or "").strip():
            print("  WARN: no DISCORD_BOT_TOKEN on bot or web — set on web manually")

    print("Web configured: Discord sidecar=1, gunicorn 2x2")


def _redeploy_chain(
    token: str, env_id: str, services: list, service_names: tuple[str, ...]
) -> None:
    for name in service_names:
        sid = _service_id(services, name)
        if not sid:
            print(f"  skip (not found): {name}")
            continue
        label = next((s["name"] for s in services if s["id"] == sid), name)
        try:
            rds._redeploy(token, sid, env_id)
            print(f"  redeploy: {label}")
        except Exception as exc:
            print(f"  WARN {label}: {exc}")


def _resolve_env_id(token: str, project_id: str) -> str:
    envs = rds._project_environments(token, project_id)
    env_id = os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip()
    if not env_id:
        for env in envs:
            if env.get("name", "").lower() == "production":
                env_id = env["id"]
                break
        if not env_id and envs:
            env_id = envs[0]["id"]
    if not env_id:
        raise RuntimeError("Could not resolve Railway environment id")
    return env_id


def _parse_services_arg(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return DEFAULT_REDEPLOY_SERVICES
    names = tuple(s.strip() for s in raw.split(",") if s.strip())
    blocked = {n.lower() for n in names} & {"postgres", "redis"}
    if blocked:
        raise ValueError(f"Refusing to redeploy database services: {blocked}")
    return names or DEFAULT_REDEPLOY_SERVICES


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--redeploy-only",
        action="store_true",
        help="Only redeploy selected services — skip variable changes",
    )
    parser.add_argument(
        "--services",
        default=",".join(DEFAULT_REDEPLOY_SERVICES),
        help="Comma-separated service names (default: web,celery-worker). Never Postgres/Redis.",
    )
    args = parser.parse_args()

    token = os.getenv("RAILWAY_TOKEN", "").strip()
    if not token:
        print("ERROR: export RAILWAY_TOKEN=...")
        print(POSTGRES_VOLUME_HELP)
        print("See docs/RAILWAY_FIX_ONCE.md")
        sys.exit(1)

    project_id = os.getenv("RAILWAY_PROJECT_ID", rds.DEFAULT_PROJECT_ID)
    base_url = os.getenv("BOT_API_BASE_URL", "https://affairsandorder.com").rstrip("/")
    env_id = _resolve_env_id(token, project_id)
    services = rds._project_services(token, project_id)
    service_names = _parse_services_arg(args.services)
    print("Services:", ", ".join(s["name"] for s in services))
    print("Redeploy targets:", ", ".join(service_names))

    if not args.redeploy_only:
        print(POSTGRES_VOLUME_HELP)
        print("\nConfiguring variables (web sidecar mode)...")
        _configure_sidecar_web(token, project_id, env_id, services, base_url)

    print("\nRedeploying selected services (Postgres/Redis excluded)...")
    _redeploy_chain(token, env_id, services, service_names)

    print("\nAfter deploy (~5 min):")
    print("  curl -s https://affairsandorder.com/ready")
    print("  curl -s https://affairsandorder.com/deploy-info")
    print("  Delete beat + bot services in dashboard once verified (see docs/RAILWAY_COST_CUT.md)")


if __name__ == "__main__":
    main()
