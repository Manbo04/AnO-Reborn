#!/usr/bin/env python3
"""Generate docs/SYSTEM_MAP.md: where things live in AnO, derived from code.

Hand-written architecture docs went stale (SYSTEM_ARCHITECTURE.md is from
2025-12). This map is rebuilt from the code itself and CI fails when it is
out of date, so it can always be trusted:

  1. background jobs: schedule + gate for every Celery beat task
  2. tables: which files WRITE and which only READ each table
     (same SQL extraction as scripts/check_sql_against_schema.py)
  3. routes: URL -> handler module:function

    python scripts/generate_system_map.py          # rewrite docs/SYSTEM_MAP.md
    python scripts/generate_system_map.py --check  # exit 1 if it is stale
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "SYSTEM_MAP.md"
sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location(
    "check_sql_against_schema", ROOT / "scripts" / "check_sql_against_schema.py"
)
chk = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = chk
_spec.loader.exec_module(chk)

WRITE_RE = re.compile(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+(?:public\.)?\"?(\w+)", re.I)
READ_RE = re.compile(r"\b(?:FROM|JOIN)\s+(?:public\.)?\"?(\w+)", re.I)
MONEY_TABLES = ("stats", "user_economy", "user_military", "user_buildings", "currency_holdings")


def schema_tables() -> set[str]:
    sql = (ROOT / "db" / "schema.sql").read_text(encoding="utf-8")
    return {m.lower() for m in re.findall(r"^CREATE TABLE public\.(\w+)", sql, re.M)}


def table_usage():
    tables = schema_tables()
    writes, reads = defaultdict(set), defaultdict(set)
    for path in sorted(chk.iter_sources()):
        rel = path.relative_to(ROOT).as_posix()
        for q in chk.extract(path):
            sql = q.sql.replace(chk.DYNAMIC_MARK, " ")
            for t in WRITE_RE.findall(sql):
                if t.lower() in tables:
                    writes[t.lower()].add(rel)
            for t in READ_RE.findall(sql):
                if t.lower() in tables:
                    reads[t.lower()].add(rel)
    return tables, writes, reads


def jobs_section() -> list[str]:
    from app_core.celery_schedule import (
        CELERY_BEAT_SCHEDULE,
        TASK_PERIODS,
        TASK_RUN_THRESHOLDS,
    )

    out = [
        "## 1. Background jobs (Celery beat)",
        "",
        "Gate: **per hour/day** = runs at most once per UTC period (`task_runs.last_period`,",
        "claimed before work -- see `app_core/game_ticks/common.py::claim_tick_period`);",
        "**min interval** = skips if `task_runs.last_run` is more recent than that.",
        "",
        "| beat entry | task | schedule (UTC) | gate |",
        "|---|---|---|---|",
    ]
    for name in sorted(CELERY_BEAT_SCHEDULE):
        entry = CELERY_BEAT_SCHEDULE[name]
        sched = re.sub(r"<crontab: (.*?) \(m/h/d/dM/MY\)>", r"`\1`", repr(entry["schedule"]))
        task = entry["task"].replace("tasks.task_", "")
        if task in TASK_PERIODS:
            gate = f"per {TASK_PERIODS[task]}"
        elif task in TASK_RUN_THRESHOLDS:
            gate = f"min interval {TASK_RUN_THRESHOLDS[task]}s"
        else:
            gate = "none (must be idempotent)"
        out.append(f"| {name} | `{entry['task']}` | {sched} | {gate} |")
    sub = sorted(t for t in TASK_PERIODS if t not in {
        e["task"].replace("tasks.task_", "") for e in CELERY_BEAT_SCHEDULE.values()
    })
    if sub:
        out += ["", "Sub-steps gated inside `global_tick` (per hour): " + ", ".join(f"`{t}`" for t in sub)]
    return out + [""]


def tables_section(tables, writes, reads) -> list[str]:
    out = [
        "## 2. Tables: who writes, who reads",
        "",
        "From every SQL statement in app code (scripts/tests excluded). Dynamic table",
        "names (f-strings) are not attributed. **Bold** = holds player money/assets:",
        "every writer listed there can create or destroy value.",
        "",
        "| table | written by | read only by |",
        "|---|---|---|",
    ]
    for t in sorted(tables):
        w = sorted(writes.get(t, ()))
        r = sorted(reads.get(t, set()) - set(w))
        if not w and not r:
            continue
        name = f"**{t}**" if t in MONEY_TABLES else t
        fmt = lambda xs: "<br>".join(f"`{x}`" for x in xs) if xs else "--"
        out.append(f"| {name} | {fmt(w)} | {fmt(r)} |")
    unused = sorted(t for t in tables if t not in writes and t not in reads)
    out += ["", "Tables no static query touches (dynamic SQL, scripts, or dead): "
            + ", ".join(f"`{t}`" for t in unused), ""]
    return out


def routes_section() -> list[str]:
    logging.disable(logging.CRITICAL)
    import database
    database.ensure_schema_compat = lambda: None
    from app import app

    rows = []
    for rule in app.url_map.iter_rules():
        if rule.endpoint == "static":
            continue
        fn = app.view_functions.get(rule.endpoint)
        target = f"{getattr(fn, '__module__', '?')}:{getattr(fn, '__name__', '?')}"
        methods = ",".join(sorted((rule.methods or set()) - {"HEAD", "OPTIONS"}))
        rows.append((rule.rule, methods, target))
    out = [
        "## 3. Routes",
        "",
        "| URL | methods | handler |",
        "|---|---|---|",
    ]
    out += [f"| `{u}` | {m} | `{h}` |" for u, m, h in sorted(rows)]
    return out + [""]


def build() -> str:
    tables, writes, reads = table_usage()
    parts = [
        "# AnO system map (generated -- do not edit by hand)",
        "",
        "Rebuilt from the code by `scripts/generate_system_map.py`; CI fails if it is stale.",
        "Intent and game rules live in `docs/GAME_RULES.md`; this file says **where** things are.",
        "",
    ]
    parts += jobs_section() + tables_section(tables, writes, reads) + routes_section()
    return "\n".join(parts).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("SECRET_KEY", "system-map")
    text = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("docs/SYSTEM_MAP.md is out of date: run python scripts/generate_system_map.py")
            return 1
        print("docs/SYSTEM_MAP.md is up to date.")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
