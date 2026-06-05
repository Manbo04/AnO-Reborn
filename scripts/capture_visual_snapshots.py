#!/usr/bin/env python3
"""Capture visual QA screenshots for key pages.

Usage:
  python3 scripts/capture_visual_snapshots.py
  DEPLOY_URL=https://affairsandorder.com python3 scripts/capture_visual_snapshots.py
"""


import os
from pathlib import Path

DEPLOY_URL = os.getenv("DEPLOY_URL", "https://affairsandorder.com").rstrip("/")
OUT = Path(os.getenv("SNAPSHOT_OUT", "artifacts/visual-snapshots"))


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        print("Playwright not installed. Install with: pip install playwright && playwright install chromium")
        return 1

    targets = [
        ("home", "/"),
        ("signup", "/signup"),
        ("country", "/country/id=1"),
        ("provinces", "/provinces"),
        ("market", "/market"),
    ]
    viewports = [
        ("desktop", {"width": 1440, "height": 900}),
        ("mobile", {"width": 390, "height": 844}),
    ]

    OUT.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp_name, viewport in viewports:
            context = browser.new_context(viewport=viewport)
            page = context.new_page()
            for name, route in targets:
                url = f"{DEPLOY_URL}{route}"
                page.goto(url, wait_until="networkidle", timeout=45000)
                path = OUT / f"{name}-{vp_name}.png"
                page.screenshot(path=str(path), full_page=True)
                print(f"Saved {path}")
            context.close()
        browser.close()

    print(f"Screenshots written to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
