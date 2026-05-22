#!/usr/bin/env python3
"""Fail CI if error(message, status_code) argument order is used in route modules."""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r'\berror\s*\(\s*["\'][^"\']+["\']\s*,\s*\d+\s*\)')

ROUTE_FILES = [
    "province.py",
    "military.py",
    "market.py",
    "countries.py",
    "coalitions.py",
    "signup.py",
    "login.py",
    "change.py",
    "wars/routes.py",
    "intelligence.py",
    "trade_agreements.py",
    "upgrades.py",
    "admin_tools.py",
]


def main():
    failures = []
    for name in ROUTE_FILES:
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for match in PATTERN.finditer(text):
            line = text[: match.start()].count("\n") + 1
            failures.append(f"{path}:{line}: {match.group(0)}")

    if failures:
        print("Found swapped error() calls (use error(status_code, message)):")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    print("error() call order check passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
