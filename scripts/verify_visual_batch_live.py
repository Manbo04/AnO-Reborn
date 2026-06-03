#!/usr/bin/env python3
"""Verify that visual batch changes are live and serving expected markers.

Usage:
  python3 scripts/verify_visual_batch_live.py
  DEPLOY_URL=https://affairsandorder.com python3 scripts/verify_visual_batch_live.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

DEPLOY_URL = os.getenv("DEPLOY_URL", "https://affairsandorder.com").rstrip("/")

PAGES_AND_MARKERS = {
    "/": ("images/game/resources/gold.svg", "templatediv"),
    "/signup": ("images/game/biomes/tundra.svg", "Choose a Biome"),
    "/country/id=1": ("country-overview-grid", "demographicsRadarChart"),
}


def _curl(path: str) -> tuple[int, str]:
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-m",
            "25",
            "-w",
            "%{http_code}",
            "-o",
            "/tmp/ano_visual_body.txt",
            f"{DEPLOY_URL}{path}",
        ],
        capture_output=True,
        text=True,
    )
    code = int((proc.stdout or "0").strip() or "0")
    try:
        body = open("/tmp/ano_visual_body.txt", encoding="utf-8").read()
    except OSError:
        body = ""
    return code, body


def _assert_deploy_fingerprint() -> bool:
    code, body = _curl("/deploy-info")
    if code != 200:
        print(f"FAIL: /deploy-info HTTP {code}")
        return False
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        print("FAIL: /deploy-info returned invalid JSON")
        return False
    live = (payload.get("git_commit") or "").strip()
    if not live or live == "unknown":
        print("FAIL: deploy-info git_commit unknown")
        return False
    print(f"OK: deploy-info commit {live[:12]}")
    return True


def _assert_css_markers() -> bool:
    code, body = _curl("/static/style.css")
    if code != 200:
        print(f"FAIL: /static/style.css HTTP {code}")
        return False
    required = ("toppershimmer", "province-node-glint", "country-overview-grid")
    missing = [m for m in required if m not in body]
    if missing:
        print(f"FAIL: style.css missing markers {missing}")
        return False
    print("OK: style.css contains vividness markers")
    return True


def _assert_page_markers() -> bool:
    ok = True
    for page, markers in PAGES_AND_MARKERS.items():
        code, body = _curl(page)
        if code != 200:
            print(f"FAIL: {page} HTTP {code}")
            ok = False
            continue
        for marker in markers:
            if marker not in body:
                print(f"FAIL: {page} missing marker {marker!r}")
                ok = False
        if ok:
            print(f"OK: {page} markers present")
    return ok


def main() -> int:
    checks = (_assert_deploy_fingerprint(), _assert_css_markers(), _assert_page_markers())
    if all(checks):
        print("OK: visual batch appears live")
        return 0
    print("FAIL: visual batch verification failed")
    return 1


if __name__ == "__main__":
    sys.exit(main())
