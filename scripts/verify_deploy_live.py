#!/usr/bin/env python3
"""Compare production /deploy-info to GitHub master (fails if players are on old code).

Usage:
  python3 scripts/verify_deploy_live.py
  DEPLOY_URL=https://affairsandorder.com python3 scripts/verify_deploy_live.py
"""

from __future__ import annotations

import json
import subprocess
import sys

DEPLOY_URL = __import__("os").getenv("DEPLOY_URL", "https://affairsandorder.com").rstrip("/")


def _curl_json(path: str) -> tuple[int, dict | str]:
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-m",
            "25",
            "-w",
            "%{http_code}",
            "-o",
            "/tmp/ano_deploy_body.txt",
            f"{DEPLOY_URL}{path}",
        ],
        capture_output=True,
        text=True,
    )
    code = int((proc.stdout or "0").strip() or "0")
    try:
        body = open("/tmp/ano_deploy_body.txt", encoding="utf-8").read()
    except OSError:
        body = ""
    if code != 200:
        return code, body[:300]
    try:
        return code, json.loads(body)
    except json.JSONDecodeError:
        return code, body[:300]


def _fetch_deploy_info() -> dict:
    status, data = _curl_json("/deploy-info")
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f"HTTP {status}: {data}")
    return data


def _github_master_sha() -> str:
    out = subprocess.check_output(
        ["git", "rev-parse", "origin/master"],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return out.strip()


def main() -> int:
    try:
        info = _fetch_deploy_info()
    except Exception as exc:
        print(f"FAIL: could not fetch {DEPLOY_URL}/deploy-info: {exc}")
        return 1

    live = (info.get("git_commit") or "unknown").strip()
    master = _github_master_sha()
    print(f"Production git_commit: {live[:12]}")
    print(f"GitHub origin/master:  {master[:12]}")

    if live.startswith("unknown") or live == "unknown":
        print("FAIL: production commit unknown")
        return 1

    if not live.startswith(master[: len(live)]) and live[:12] != master[:12]:
        print("\nFAIL: production is BEHIND GitHub master — players will NOT see latest fixes.")
        print("Fix:")
        print("  1. Railway dashboard → web → Deploy (or Redeploy)")
        print("  2. Redeploy celery-worker + beat (economy tasks)")
        print("  3. Or set GitHub secret RAILWAY_TOKEN and push to master")
        return 1

    print("\nOK: production commit matches origin/master prefix")

    economy = info.get("economy_tasks") or {}
    if economy:
        rev = economy.get("generate_province_revenue") or {}
        if rev.get("stale"):
            print(
                f"WARN: generate_province_revenue stale "
                f"(age_seconds={rev.get('age_seconds')}) — restart beat + worker"
            )
            return 1
        print("OK: economy_tasks present and revenue not stale")
    else:
        print("WARN: deploy-info has no economy_tasks (older web build)")

    status, data = _curl_json("/ready")
    if status != 200:
        print(f"WARN: /ready HTTP {status}: {data}")
        return 1

    print("OK: /ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
