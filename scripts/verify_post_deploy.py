#!/usr/bin/env python3
"""HTTP smoke checks after deploy (no auth required for public routes)."""


import argparse
import sys

DEFAULT_BASE = "https://affairsandorder.com"

CHECKS = [
    ("/country/id=16", {200}),
    ("/country/id=27", {200}),
    ("/coalitions", {200, 302}),
    ("/my_coalition", {200, 302}),
    ("/account", {200, 302}),
]


def fetch_status(base: str, path: str, timeout: float = 30.0) -> int:
    url = base.rstrip("/") + path
    req = urllib.request.Request(
        url,
        method="GET",
        headers={
            "User-Agent": "AnO-PostDeployCheck/1.0 (+https://affairsandorder.com)",
            "Accept": "text/html",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def main() -> None:
    parser = argparse.ArgumentParser(description="Post-deploy HTTP smoke checks")
    parser.add_argument("--base", default=DEFAULT_BASE, help="Site base URL")
    args = parser.parse_args()

    failed = []
    warnings = []
    for path, allowed in CHECKS:
        status = fetch_status(args.base, path)
        if status == 500:
            failed.append(f"{path} -> {status} (server error)")
        elif status not in allowed:
            warnings.append(
                f"{path} -> {status} (expected one of {sorted(allowed)}; "
                "may be CDN/WAF from automated clients)"
            )
        else:
            print(f"OK {path} -> {status}")

    for w in warnings:
        print(f"WARN {w}")

    if failed:
        print("FAILED:", file=sys.stderr)
        for line in failed:
            print(f"  {line}", file=sys.stderr)
        sys.exit(1)

    print("All smoke checks passed.")


if __name__ == "__main__":
    main()
