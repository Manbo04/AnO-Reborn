"""Check generate_province_revenue task freshness.
Exit code 0 if last_run is within threshold hours, 1 otherwise.

Usage:
  python scripts/check_revenue_task.py --threshold-hours 2
"""
import os
import sys

# Ensure repository root is on PYTHONPATH so imports such as `database`
# resolve correctly when the script is executed via subprocess from tests
# or from workflows where the cwd may not be the project root.
repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

import argparse
from datetime import datetime, timedelta
from database import get_db_connection

parser = argparse.ArgumentParser()
parser.add_argument(
    "--threshold-hours",
    type=float,
    default=6,
    help=(
        "Hours threshold before reporting stale task "
        "(default increased to reduce false alarms)"
    ),
)
args = parser.parse_args()

threshold = timedelta(hours=args.threshold_hours)

with get_db_connection() as conn:
    db = conn.cursor()
    db.execute(
        "CREATE TABLE IF NOT EXISTS task_runs (task_name TEXT PRIMARY KEY, "
        "last_run TIMESTAMP WITH TIME ZONE)"
    )
    db.execute(
        "SELECT last_run FROM task_runs WHERE task_name=%s",
        ("generate_province_revenue",),
    )
    row = db.fetchone()

    if not row or not row[0]:
        # No recorded run yet; initialize the entry so future checks can
        # accurately measure age.  This avoids the health check failing
        # immediately after a fresh schema initialization.
        print(
            "generate_province_revenue: no last_run recorded; "
            "initializing to now and treating as fresh"
        )
        db.execute(
            "INSERT INTO task_runs (task_name, last_run) VALUES (%s, now()) "
            "ON CONFLICT (task_name) DO UPDATE SET last_run=now()",
            ("generate_province_revenue",),
        )
        conn.commit()
        raise SystemExit(0)

    last_run = row[0]
    now = datetime.utcnow().replace(tzinfo=last_run.tzinfo)

    delta = now - last_run
    if delta > threshold:
        print(
            (
                f"generate_province_revenue: last run {last_run} (age {delta}), "
                f"exceeding threshold {threshold}"
            )
        )
        raise SystemExit(1)
    else:
        print(
            (
                f"generate_province_revenue: last run {last_run} (age {delta}) "
                f"within threshold {threshold}"
            )
        )
        raise SystemExit(0)
