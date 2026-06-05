#!/usr/bin/env python3
"""Rank recurring patterns in Railway/Gunicorn log exports.

Usage:
    python3 scripts/analyze_railway_logs.py path/to/logs.log
    python3 scripts/analyze_railway_logs.py docs/logs/*.log
"""


import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "docs" / "BACKEND_LOG_TRIAGE.md"

BUCKETS: list[tuple[str, re.Pattern]] = [
    ("HTTP_500", re.compile(r"\[ERROR! \^+\]|Invalid Server Error|Internal Server Error", re.I)),
    ("LOGIN", re.compile(r"POST /login|Unhandled exception during login|Wrong password", re.I)),
    ("SCHEMA", re.compile(r"ensure_schema_compat|schema_compat|UndefinedColumn|does not exist", re.I)),
    ("DB_POOL", re.compile(r"pool exhausted|InterfaceError|OperationalError|too many connections", re.I)),
    ("CELERY_BEAT", re.compile(r"beat leader lock|celery beat exited|run_beat_if_leader", re.I)),
    ("CELERY_TASK", re.compile(r"START OF EXCEPTION|deadlock detected|already in progress|global_tick watchdog", re.I)),
    ("ECONOMY", re.compile(r"generate_province_revenue|user_economy|tax_income|population_growth", re.I)),
    ("MARKET_COALITION", re.compile(r"give_resource|colBanksRequests|buy_market_offer", re.I)),
    ("CSRF", re.compile(r"CSRF|csrf", re.I)),
]


def _normalize_line(line: str) -> str:
    line = line.strip()
    line = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "<ts>", line)
    line = re.sub(r"[a-z0-9]{20}-\d{10}", "<error_id>", line)
    line = re.sub(r"\b\d+\b", "<n>", line)
    return line[:200]


def analyze_file(path: Path) -> tuple[Counter, Counter, int]:
    bucket_counts: Counter = Counter()
    signature_counts: Counter = Counter()
    lines_read = 0
    text = path.read_text(encoding="utf-8", errors="replace")
    for raw in text.splitlines():
        lines_read += 1
        for name, pat in BUCKETS:
            if pat.search(raw):
                bucket_counts[name] += 1
                signature_counts[_normalize_line(raw)] += 1
                break
    return bucket_counts, signature_counts, lines_read


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", help="Log file path(s)")
    args = parser.parse_args()

    paths = []
    for arg in args.logs:
        p = Path(arg)
        if p.is_file():
            paths.append(p)
        else:
            print(f"WARN: not a file: {p}", file=sys.stderr)

    if not paths:
        print("No log files found. Add logs under docs/logs/ — see docs/logs/README.md")
        return 1

    total_buckets: Counter = Counter()
    total_sigs: Counter = Counter()
    total_lines = 0
    for path in paths:
        b, s, n = analyze_file(path)
        total_buckets.update(b)
        total_sigs.update(s)
        total_lines += n

    lines_out = [
        "# Backend log triage (auto-generated)",
        "",
        f"- Files: {', '.join(p.name for p in paths)}",
        f"- Lines scanned: {total_lines}",
        "",
        "## Bucket counts",
        "",
        "| Bucket | Hits |",
        "|--------|------|",
    ]
    for name, _ in BUCKETS:
        lines_out.append(f"| {name} | {total_buckets.get(name, 0)} |")

    lines_out.extend(["", "## Top signatures (normalized)", ""])
    for sig, count in total_sigs.most_common(25):
        if not sig:
            continue
        lines_out.append(f"- ({count}) `{sig}`")

    lines_out.extend(
        [
            "",
            "## Suggested priority",
            "",
            "1. **LOGIN** / **HTTP_500** on `POST /login` — policies row ensure, CSRF token on form",
            "2. **SCHEMA** — run `apply_all_pending_migrations.py`, verify `/deploy-info`",
            "3. **CELERY_BEAT** / **ECONOMY** — beat leader lock, `progression_health_check.py`",
            "4. **DB_POOL** — pool size vs replica count",
            "",
        ]
    )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text("\n".join(lines_out), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
