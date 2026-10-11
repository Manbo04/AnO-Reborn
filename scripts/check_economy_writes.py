#!/usr/bin/env python3
"""Block new raw writes to stats.gold / user_economy outside the ledger.

Money and resources should change through app_core/economy/ledger.py.
Older code still writes directly; scripts/economy_write_baseline.json
records how many raw writes each file has. CI fails if a file gains one
(or a new file starts writing). When you move writes into the ledger,
run with --update to lower the baseline.
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "economy_write_baseline.json"
EXEMPT_DIRS = {"tests", "scripts", "migrations", ".git", "venv", ".venv", "node_modules"}
LEDGER = "app_core/economy/ledger.py"

PATTERNS = [
    re.compile(r"UPDATE\s+stats\b[^;]*?\bSET\b[^;]*?\bgold\s*=", re.I | re.S),
    re.compile(r"UPDATE\s+user_economy\b", re.I),
    re.compile(r"INSERT\s+INTO\s+user_economy\b", re.I),
]


def scan():
    counts = {}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel.split("/")[0] in EXEMPT_DIRS or rel == LEDGER:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Keep UPDATE stats matches inside one statement-ish window.
        n = 0
        for pat in PATTERNS:
            for m in pat.finditer(text):
                if len(m.group(0)) < 400:
                    n += 1
        if n:
            counts[rel] = n
    return counts


def main():
    counts = scan()
    if "--update" in sys.argv:
        BASELINE.write_text(json.dumps(dict(sorted(counts.items())), indent=2) + "\n")
        print(f"baseline written: {sum(counts.values())} raw writes in {len(counts)} files")
        return 0
    baseline = json.loads(BASELINE.read_text())
    bad = [(f, n, baseline.get(f, 0)) for f, n in sorted(counts.items()) if n > baseline.get(f, 0)]
    if bad:
        print("New raw gold/user_economy writes. Use app_core/economy/ledger.py instead:")
        for f, n, b in bad:
            print(f"  {f}: {n} (baseline {b})")
        return 1
    stale = [f for f in baseline if counts.get(f, 0) < baseline[f]]
    if stale:
        print("Fewer raw writes than baseline in: " + ", ".join(stale) + " (run with --update)")
    print(f"economy writes ok: {sum(counts.values())} raw writes left in {len(counts)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
