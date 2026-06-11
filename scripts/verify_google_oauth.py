#!/usr/bin/env python3
"""Verify Google OAuth is configured and production /login/google redirects to Google."""
from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app_core.auth.google_auth import get_google_redirect_uri, is_google_auth_configured  # noqa: E402


def main() -> int:
    base = os.getenv("VERIFY_BASE_URL", "https://affairsandorder.com").rstrip("/")
    errors: list[str] = []

    if is_google_auth_configured():
        print("OK: Google OAuth env vars present in this shell")
    else:
        print("Note: local shell has no Google vars (checking production remote state)")

    redirect_uri = get_google_redirect_uri()
    print(f"Redirect URI: {redirect_uri}")

    try:
        resp = requests.get(f"{base}/login/google", allow_redirects=False, timeout=20)
    except requests.RequestException as exc:
        errors.append(f"Could not reach {base}/login/google: {exc}")
        _report(errors)
        return 1

    location = resp.headers.get("Location", "")
    print(f"GET /login/google -> HTTP {resp.status_code}")
    if location:
        print(f"Location: {location[:120]}...")

    if resp.status_code == 302 and "accounts.google.com" in location:
        print("OK: /login/google redirects to Google OAuth")
    elif resp.status_code == 302 and "/login" in location:
        errors.append(
            "Server redirected back to /login (Google OAuth not configured on production)."
        )
    else:
        errors.append(
            f"Expected 302 to accounts.google.com, got {resp.status_code} "
            f"location={location!r}"
        )

    try:
        login_html = requests.get(f"{base}/login", timeout=20).text
        if "login/google" in login_html and "Google Login" in login_html:
            print("OK: Login page shows Google button")
        elif "login/google" not in login_html:
            errors.append("Login page does not include Google login link (vars may be unset).")
    except requests.RequestException as exc:
        errors.append(f"Could not load login page: {exc}")

    _report(errors)
    return 1 if errors else 0


def _report(errors: list[str]) -> None:
    if not errors:
        print("\nAll Google OAuth checks passed.")
        return
    print("\nFAILURES:")
    for err in errors:
        print(f"  - {err}")


if __name__ == "__main__":
    raise SystemExit(main())
