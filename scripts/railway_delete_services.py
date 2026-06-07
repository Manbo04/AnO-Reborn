#!/usr/bin/env python3
"""Delete Railway services by name (e.g. beat, bot after cost-cut consolidation).

Usage:
  RAILWAY_TOKEN=... python3 scripts/railway_delete_services.py beat bot
"""
from __future__ import annotations

import json
import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import railway_discord_bot_setup as rds  # noqa: E402


def _token() -> str:
    token = os.getenv("RAILWAY_TOKEN", "").strip()
    if token:
        return token
    cfg_path = os.path.expanduser("~/.railway/config.json")
    if os.path.isfile(cfg_path):
        with open(cfg_path, encoding="utf-8") as fh:
            return json.load(fh).get("user", {}).get("token", "").strip()
    return ""


def delete_services(names: list[str]) -> int:
    token = _token()
    if not token:
        print("ERROR: set RAILWAY_TOKEN or run `railway login`")
        return 1

    project_id = os.getenv("RAILWAY_PROJECT_ID", rds.DEFAULT_PROJECT_ID)
    services = rds._project_services(token, project_id)
    by_name = {s["name"].lower(): s for s in services}
    print("Current:", ", ".join(s["name"] for s in services))

    for name in names:
        svc = by_name.get(name.lower())
        if not svc:
            print(f"  skip {name}: not found")
            continue
        rds._gql(
            token,
            "mutation($id: String!) { serviceDelete(id: $id) }",
            {"id": svc["id"]},
        )
        print(f"  deleted: {svc['name']}")

    remaining = rds._project_services(token, project_id)
    print("Remaining:", ", ".join(s["name"] for s in remaining))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/railway_delete_services.py beat bot")
        raise SystemExit(1)
    raise SystemExit(delete_services(sys.argv[1:]))
