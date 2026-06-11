#!/usr/bin/env python3
"""Trim Railway spend: delete stale PR/dev environments + cap production resources.

Keeps Pro plan (multi-region). Target: total bill under $30/month.

Usage:
  python3 scripts/railway_cost_trim.py --dry-run
  python3 scripts/railway_cost_trim.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import railway_discord_bot_setup as rds  # noqa: E402

DEFAULT_PROJECT_ID = rds.DEFAULT_PROJECT_ID
PRODUCTION_ENV_NAME = "production"

# Delete every non-production environment (PR previews, recovery, development).
DELETE_ENV_NAMES = None  # resolved at runtime

PRODUCTION_LIMITS: dict[str, dict[str, float]] = {
    "web": {"memoryGB": 0.5, "vCPUs": 1},
    "celery-worker": {"memoryGB": 0.5, "vCPUs": 1},
    "prod-validator": {"memoryGB": 1.0, "vCPUs": 1},
    "Redis": {"memoryGB": 0.5, "vCPUs": 0.5},
}

PRODUCTION_VARS: dict[str, dict[str, str]] = {
    "web": {
        "GUNICORN_WORKERS": "1",
        "GUNICORN_THREADS": "2",
        "DEBUG_RECOVERY": "false",
        "DB_MAX_CONNECTIONS": "6",
    },
    "celery-worker": {
        "CELERY_CONCURRENCY": "1",
        "DB_MAX_CONNECTIONS": "6",
    },
}


def _token() -> str:
    token = os.getenv("RAILWAY_TOKEN", "").strip()
    if token:
        return token
    cfg_path = os.path.expanduser("~/.railway/config.json")
    with open(cfg_path, encoding="utf-8") as fh:
        return json.load(fh)["user"]["token"].strip()


def _active_services(token: str, project_id: str, env_id: str) -> list[str]:
    data = rds._gql(
        token,
        """
        query($pid: String!) {
          project(id: $pid) {
            services { edges { node { name serviceInstances { edges { node {
              environmentId latestDeployment { status }
            } } } } } }
          }
        }
        """,
        {"pid": project_id},
    )
    names = []
    for edge in data["project"]["services"]["edges"]:
        node = edge["node"]
        for inst_edge in node["serviceInstances"]["edges"]:
            inst = inst_edge["node"]
            if inst["environmentId"] != env_id:
                continue
            status = (inst.get("latestDeployment") or {}).get("status")
            if status in ("SUCCESS", "ACTIVE", "DEPLOYING", "BUILDING"):
                names.append(node["name"])
    return names


def _delete_environment(token: str, env_id: str, env_name: str, dry_run: bool) -> None:
    active = _active_services(token, DEFAULT_PROJECT_ID, env_id)
    label = f"{env_name} ({len(active)} active: {', '.join(active) or 'none'})"
    if dry_run:
        print(f"  [dry-run] delete environment: {label}")
        return
    rds._gql(
        token,
        "mutation($id: String!) { environmentDelete(id: $id) }",
        {"id": env_id},
    )
    print(f"  deleted environment: {label}")


def _set_limits(
    token: str,
    env_id: str,
    service_id: str,
    service_name: str,
    limits: dict[str, float],
    dry_run: bool,
) -> None:
    mem = limits["memoryGB"]
    cpu = limits.get("vCPUs", 1)
    if dry_run:
        print(f"  [dry-run] limits {service_name}: {mem}GB RAM, {cpu} vCPU")
        return
    rds._gql(
        token,
        """
        mutation($input: ServiceInstanceLimitsUpdateInput!) {
          serviceInstanceLimitsUpdate(input: $input)
        }
        """,
        {
            "input": {
                "environmentId": env_id,
                "serviceId": service_id,
                "memoryGB": mem,
                "vCPUs": cpu,
            }
        },
    )
    print(f"  limits {service_name}: {mem}GB RAM, {cpu} vCPU")


def _apply_vars(
    token: str,
    project_id: str,
    env_id: str,
    services: list[dict],
    dry_run: bool,
) -> None:
    by_name = {s["name"]: s["id"] for s in services}
    for svc_name, vars_map in PRODUCTION_VARS.items():
        sid = by_name.get(svc_name)
        if not sid:
            print(f"  skip vars (missing service): {svc_name}")
            continue
        for key, value in vars_map.items():
            if dry_run:
                print(f"  [dry-run] {svc_name} {key}={value}")
                continue
            rds._upsert_var(token, project_id, env_id, sid, key, value)
        if not dry_run:
            print(f"  vars updated: {svc_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Apply changes (default: dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only")
    args = parser.parse_args()
    dry_run = not args.apply
    if args.dry_run:
        dry_run = True

    token = _token()
    project_id = os.getenv("RAILWAY_PROJECT_ID", DEFAULT_PROJECT_ID)
    envs = rds._project_environments(token, project_id)
    services = rds._project_services(token, project_id)
    by_name = {s["name"]: s for s in services}

    prod = next((e for e in envs if e["name"] == PRODUCTION_ENV_NAME), None)
    if not prod:
        print("ERROR: production environment not found")
        return 1
    prod_id = prod["id"]

    print("=== Railway cost trim ===")
    print("Mode:", "DRY-RUN" if dry_run else "APPLY")
    print("Services:", ", ".join(s["name"] for s in services))
    print()

    stale = [e for e in envs if e["name"] != PRODUCTION_ENV_NAME]
    print(f"Stale environments to remove ({len(stale)}):")
    for env in stale:
        _delete_environment(token, env["id"], env["name"], dry_run)
    print()

    print("Production resource caps:")
    for svc_name, limits in PRODUCTION_LIMITS.items():
        svc = by_name.get(svc_name)
        if not svc:
            print(f"  skip limits (missing): {svc_name}")
            continue
        _set_limits(token, prod_id, svc["id"], svc_name, limits, dry_run)
    print()

    print("Production lean env vars:")
    _apply_vars(token, project_id, prod_id, services, dry_run)
    print()

    if dry_run:
        print("No changes applied. Re-run with: python3 scripts/railway_cost_trim.py --apply")
    else:
        print("Redeploying web + celery-worker to pick up slimmer settings...")
        from railway_production_fix import _redeploy_chain

        _redeploy_chain(token, prod_id, services, ("web", "celery-worker"))
        print()
        print("Done. In Railway dashboard → Usage, set Compute Usage Limit to $30.")
        print("Monitor Usage for 48h — stale PR envs were the main leak.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
