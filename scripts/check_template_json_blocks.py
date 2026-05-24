#!/usr/bin/env python3
"""Fail CI if templates use JSON.parse with raw Jinja without tojson."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

BAD = re.compile(r"JSON\.parse\s*\(\s*['\"]?\{\{", re.IGNORECASE)


def main() -> int:
    failed = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if BAD.search(line) and "| tojson" not in line:
                failed.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()[:120]}")
    if failed:
        print("Unsafe JSON.parse blocks (use | tojson):")
        for item in failed:
            print(f"  {item}")
        return 1
    print("OK: no unsafe JSON.parse patterns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
