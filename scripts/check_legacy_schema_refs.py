#!/usr/bin/env python3
"""Fail CI if production Python modules reference dropped legacy tables."""


import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"tests", "scripts", "venv310", ".venv_test", "mcp-server", "node_modules", ".venv", "venv"}
PATTERNS = [
    re.compile(r"\bFROM\s+proInfra\b", re.I),
    re.compile(r"\bFROM\s+resources\b", re.I),
    re.compile(r"\bINTO\s+proInfra\b", re.I),
]


def main() -> int:
    failed = []
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.name.startswith("test_"):
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if any(pat.search(line) for pat in PATTERNS):
                failed.append(str(path.relative_to(ROOT)))
                break
    if failed:
        print("Legacy table references in non-test code:")
        for f in sorted(set(failed)):
            print(f"  {f}")
        return 1
    print("OK: no legacy proInfra/resources SQL in app modules")
    return 0


if __name__ == "__main__":
    sys.exit(main())
