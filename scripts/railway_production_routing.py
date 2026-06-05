#!/usr/bin/env python3
r"""Audit Railway environments vs live domain, then redeploy the correct production stack.

Requires:
  export RAILWAY_TOKEN='...'   # Railway account token (Settings → Tokens)

Usage:
  # 1) See all environments + web host hints
  python3 scripts/railway_production_routing.py audit

  # 2) Redeploy web + celery-worker + beat in production (by env name)
  export RAILWAY_ENVIRONMENT_ID='<production-env-id>'   # optional if env is named production
  python3 scripts/railway_production_routing.py deploy

  # 3) Verify live site picked up master + Discord widget
  python3 scripts/verify_deploy_live.py
  curl -sS https://affairsandorder.com/ | rg 'discord(app)?\.com/widget\?id=[0-9]+' -o
"""


import json
import os
import subprocess
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import railway_discord_bot_setup as rds  # noqa: E402

PROJECT_ID = os.getenv("RAILWAY_PROJECT_ID", rds.DEFAULT_PROJECT_ID)
LIVE_DOMAIN = os.getenv("DEPLOY_URL", "https://affairsandorder.com").rstrip("/")

# From GitHub commit statuses (natural-gratitude project) — use audit to refresh.
KNOWN_ENVS = {
    "ddb0dc4f-2241-4329-91e8-6ab3e2d4cac9": "CI web deploy target (web-development-480b…)",
    "e60f87d0-5b60-4036-98fb-03eb0caa61e6": "alternate env (older beat check)",
    "9fca4083-72ee-4a48-9e80-6676904431f5": "alternate env (older beat check)",
}


def _curl(path: str, host: str | None = None) -> tuple[int, str]:
    base = host if host else LIVE_DOMAIN
    url = f"{base.rstrip('/')}{path}"
    try:
        proc = subprocess.run(
            ["curl", "-sS", "-m", "25", "-w", "%{http_code}", "-o", "/tmp/railway_route_body.txt", url],
            capture_output=True,
            text=True,
        )
        code = int((proc.stdout or "0").strip() or "0")
        try:
            body = open("/tmp/railway_route_body.txt", encoding="utf-8").read()
        except OSError:
            body = ""
        return code, body
    except Exception as exc:
        return 0, str(exc)


def _live_fingerprint() -> dict:
    code, body = _curl("/deploy-info")
    if code != 200:
        return {"error": f"deploy-info HTTP {code}", "body": body[:300]}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"error": "invalid json", "body": body[:300]}
    _, html = _curl("/")
    import re

    m = re.search(r"discord(?:app)?\.com/widget\?id=(\d+)", html)
    return {
        "git_commit": (data.get("git_commit") or "unknown")[:12],
        "schema_compat": data.get("schema_compat"),
        "start_command": data.get("start_command"),
        "discord_widget_id": m.group(1) if m else None,
    }


def cmd_audit(token: str) -> int:
    print(f"Project: {PROJECT_ID}")
    print(f"Live domain fingerprint ({LIVE_DOMAIN}):")
    fp = _live_fingerprint()
    for k, v in fp.items():
        print(f"  {k}: {v}")
    print()

    envs = rds._project_environments(token, PROJECT_ID)
    services = rds._project_services(token, PROJECT_ID)
    web_id = next((s["id"] for s in services if s["name"].lower() == "web"), None)

    print("Environments:")
    for env in envs:
        eid = env["id"]
        name = env.get("name", "?")
        hint = KNOWN_ENVS.get(eid, "")
        print(f"  - {name} ({eid}) {hint}")

        if not web_id:
            continue
        try:
            vars_ = rds._get_service_variables(token, PROJECT_ID, eid, web_id)
        except Exception as exc:
            print(f"      web vars: ERROR {exc}")
            continue
        db = "set" if vars_.get("DATABASE_URL") or vars_.get("DATABASE_PUBLIC_URL") else "MISSING"
        print(f"      web DATABASE_URL: {db}")
        for key in ("RAILWAY_PUBLIC_DOMAIN", "RAILWAY_STATIC_URL", "RAILWAY_SERVICE_WEB_URL"):
            if vars_.get(key):
                print(f"      {key}: {vars_[key]}")

    print("\nWhat to fix:")
    print("  1) Custom domain must attach to the SAME environment you deploy from GitHub.")
    print("  2) web DATABASE_URL in that environment must reference the live Postgres (not wrong password).")
    print("  3) After deploy: git_commit on /deploy-info must match origin/master; widget id 708006319658893385.")
    print("\nRedeploy production:")
    print("  export RAILWAY_ENVIRONMENT_ID='<id-of-env-that-owns affairsandorder.com>'")
    print("  python3 scripts/railway_production_routing.py deploy")
    return 0


def _resolve_production_env_id(token: str) -> str:
    explicit = os.getenv("RAILWAY_ENVIRONMENT_ID", "").strip()
    if explicit:
        return explicit
    envs = rds._project_environments(token, PROJECT_ID)
    for env in envs:
        if env.get("name", "").lower() == "production":
            return env["id"]
    names = ", ".join(f"{e.get('name')}({e['id']})" for e in envs)
    raise RuntimeError(
        "Set RAILWAY_ENVIRONMENT_ID to the environment that serves affairsandorder.com. "
        f"Available: {names}"
    )


def cmd_deploy(token: str) -> int:
    env_id = _resolve_production_env_id(token)
    services = rds._project_services(token, PROJECT_ID)
    print(f"Redeploying in environment {env_id}")
    for name in ("web", "celery-worker", "beat", "bot"):
        sid = next((s["id"] for s in services if s["name"].lower() == name.lower()), None)
        if not sid:
            print(f"  skip {name}: not found")
            continue
        try:
            rds._redeploy(token, sid, env_id)
            print(f"  redeployed {name}")
        except Exception as exc:
            print(f"  WARN {name}: {exc}")
    print("\nWait ~3–5 min, then:")
    print("  python3 scripts/verify_deploy_live.py")
    print("  curl -sS https://affairsandorder.com/ | rg 'discord.com/widget\\?id=' -o")
    return 0


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Railway production routing audit/deploy")
    parser.add_argument("command", choices=("audit", "deploy"), nargs="?", default="audit")
    args = parser.parse_args()

    token = os.getenv("RAILWAY_TOKEN", "").strip()
    if not token:
        print("ERROR: RAILWAY_TOKEN is not set.")
        print("Get one: Railway dashboard → Account Settings → Tokens → Create")
        print("Then: export RAILWAY_TOKEN='...'")
        return 1

    if args.command == "audit":
        return cmd_audit(token)
    return cmd_deploy(token)


if __name__ == "__main__":
    sys.exit(main())
