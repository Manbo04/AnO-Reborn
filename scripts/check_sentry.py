#!/usr/bin/env python3
"""Simple Sentry checker used by CI.

Exits with code 0 if no recent Sentry issues were found for the project/environment.
Exits with non-zero if recent issues were found (so CI can fail the job).

Requires env vars:
- SENTRY_AUTH_TOKEN
- SENTRY_ORG
- SENTRY_PROJECT
- SENTRY_ENV (defaults to 'staging')

Usage: python scripts/check_sentry.py --lookback-minutes 15
"""

import os
import sys
import argparse
import time
from datetime import datetime, timedelta
import requests


def iso_to_dt(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-minutes", type=int, default=15)
    args = parser.parse_args()

    token = os.getenv("SENTRY_AUTH_TOKEN")
    org = os.getenv("SENTRY_ORG")
    project = os.getenv("SENTRY_PROJECT")
    env = os.getenv("SENTRY_ENV", "staging")

    if not token or not org or not project:
        print("Sentry check skipped: missing SENTRY_AUTH_TOKEN, SENTRY_ORG or SENTRY_PROJECT env vars")
        return 0

    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://sentry.io/api/0/projects/{org}/{project}/issues/"

    try:
        params = {"query": f"environment:{env}", "limit": 100}
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        issues = r.json()

        now = datetime.utcnow()
        cutoff = now - timedelta(minutes=args.lookback_minutes)

        recent = []
        for issue in issues:
            last_seen = issue.get("lastSeen")
            dt = iso_to_dt(last_seen) if last_seen else None
            if dt and dt.replace(tzinfo=None) >= cutoff:
                recent.append({"id": issue.get("id"), "title": issue.get("title"), "lastSeen": last_seen})

        if recent:
            print(f"Sentry: Found {len(recent)} recent issue(s) in environment '{env}' (last {args.lookback_minutes} minutes)")
            for i in recent:
                print(f"- {i['id']}: {i['title']} (lastSeen={i['lastSeen']})")
            # Fail the CI job
            return 2
        else:
            print(f"Sentry: No recent issues in environment '{env}' (last {args.lookback_minutes} minutes)")
            return 0

    except requests.RequestException as e:
        print(f"Sentry check failed: {e}")
        return 1


if __name__ == '__main__':
    rc = main()
    sys.exit(rc)
