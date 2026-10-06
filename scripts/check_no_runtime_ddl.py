#!/usr/bin/env python3
"""Fail if app code alters the schema at runtime.

Schema changes belong in migrations/ (applied once, tested in CI against the
production schema snapshot). `ALTER TABLE` inside a request handler or a tick
takes an ACCESS EXCLUSIVE lock on the table every time it runs -- even when the
column already exists -- which is how the 2026-09-09 lock pile-up happened.

ALLOWED lists files that still do this today. It may only shrink.
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "tests", "scratch", "scripts",
    "debug_scripts", "attack_scripts", "migrations", "mcp-server", "graphify-out",
    "__pycache__", ".agents", ".claude",
}
ALLOWED = {
    "add_recovery_key.py",     # one-off root script
    "affo/create_db.py",       # legacy bootstrap
    "database.py",             # ensure_schema_compat(), runs at deploy boot
    "init_db_railway.py",      # bootstrap for empty databases
    "migrate.py",              # legacy migration helper
    "signup.py",               # signup_attempts compat, once per process
}
DDL = re.compile(r"\b(ALTER\s+TABLE|DROP\s+TABLE|DROP\s+COLUMN)\b", re.I)


def main() -> int:
    bad = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for name in filenames:
            if not name.endswith(".py") or name.startswith("._"):
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(ROOT).as_posix()
            if rel in ALLOWED:
                continue
            for n, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if DDL.search(line):
                    bad.append(f"{rel}:{n}: {line.strip()[:100]}")
    for b in bad:
        print("ERROR runtime DDL:", b)
    if bad:
        print("\nPut schema changes in migrations/YYYYMMDD_HHMM_name.sql instead (see CLAUDE.md).")
        return 1
    print("No runtime DDL outside the allowlist.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
