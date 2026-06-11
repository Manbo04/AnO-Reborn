#!/usr/bin/env python3
"""
Print Google Cloud OAuth setup steps and optionally set Railway web service variables.

Usage:
  # Show setup checklist only
  python3 scripts/setup_google_oauth_railway.py

  # Apply credentials to Railway (reads env or flags)
  GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com \\
  GOOGLE_CLIENT_SECRET=yyy \\
  python3 scripts/setup_google_oauth_railway.py --apply
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

SETUP_STEPS = """
Google Cloud OAuth setup (one-time, ~10 minutes)
==============================================
1. Open https://console.cloud.google.com/apis/credentials
2. Configure OAuth consent screen (External):
   - App name: Affairs and Order
   - Authorized domain: affairsandorder.com
   - Add your Gmail as a Test user (required while app is in Testing)
3. Create Credentials → OAuth client ID → Web application
4. Authorized JavaScript origins:
     https://affairsandorder.com
5. Authorized redirect URIs (add BOTH):
     https://affairsandorder.com/login/google/callback
     https://www.affairsandorder.com/login/google/callback
6. Copy Client ID and Client secret, then run:

   GOOGLE_CLIENT_ID="<id>" GOOGLE_CLIENT_SECRET="<secret>" \\
     python3 scripts/setup_google_oauth_railway.py --apply

7. Verify:
   python3 scripts/verify_google_oauth.py
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Google OAuth Railway setup helper")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET on Railway web service",
    )
    parser.add_argument("--client-id", default=os.getenv("GOOGLE_CLIENT_ID", "").strip())
    parser.add_argument(
        "--client-secret", default=os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    )
    args = parser.parse_args()

    print(SETUP_STEPS.strip())

    if not args.apply:
        print("\n(Dry run — pass --apply with credentials to update Railway.)")
        return 0

    if not args.client_id or not args.client_secret:
        print(
            "\nERROR: Missing GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET.",
            file=sys.stderr,
        )
        return 1

    for name, value in (
        ("GOOGLE_CLIENT_ID", args.client_id),
        ("GOOGLE_CLIENT_SECRET", args.client_secret),
    ):
        cmd = [
            "railway",
            "variables",
            "set",
            f"{name}={value}",
            "--service",
            "web",
        ]
        print(f"\nRunning: railway variables set {name}=*** --service web")
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr or result.stdout, file=sys.stderr)
            return result.returncode
        print(result.stdout.strip() or f"OK: set {name}")

    print("\nRailway will redeploy automatically. Then run:")
    print("  python3 scripts/verify_google_oauth.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
