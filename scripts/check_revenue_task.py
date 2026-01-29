"""Check generate_province_revenue task freshness.
Exit code 0 if last_run is within threshold hours, 1 otherwise.

Usage:
  python scripts/check_revenue_task.py --threshold-hours 2
"""
import argparse
from datetime import datetime, timedelta
from database import get_db_connection

parser = argparse.ArgumentParser()
parser.add_argument(
    "--threshold-hours",
    type=float,
    default=2,
    help="Hours threshold before reporting stale task",
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
        print("generate_province_revenue: no last_run recorded; considered stale")
        raise SystemExit(1)

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
