import os
import subprocess
import sys
from datetime import datetime, timedelta

from database import get_db_connection


def run_script(threshold_hours: float):
    # Invoke the health‑check script with a given threshold and return
    # the CompletedProcess object.
    env = os.environ.copy()
    # Make sure the repo root is on PYTHONPATH for the subprocess so
    # the `database` module can be imported.  CI already sets PYTHONPATH,
    # but tests execute locally too.
    env["PYTHONPATH"] = env.get("PYTHONPATH", "") + os.pathsep + os.getcwd()
    # ensure we run with the same interpreter used for tests
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/check_revenue_task.py",
            "--threshold-hours",
            str(threshold_hours),
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    return proc


def test_check_revenue_initializes_row():
    # start with no task_runs table at all; script should create it and seed a row
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS task_runs")
        conn.commit()

    result = run_script(threshold_hours=10)
    assert result.returncode == 0, f"script failed: {result.stderr}\n{result.stdout}"
    assert "initializing to now" in result.stdout

    # verify the row now exists and is recent
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT last_run FROM task_runs WHERE task_name=%s",
            ("generate_province_revenue",),
        )
        row = cur.fetchone()
        assert row and row[0] is not None
        # last_run should be within a minute of now
        age = datetime.utcnow().replace(tzinfo=row[0].tzinfo) - row[0]
        assert age < timedelta(minutes=1)


def test_check_revenue_detects_stale():
    # ensure table exists and insert an ancient timestamp
    past = datetime.utcnow() - timedelta(hours=5)
    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            (
                "CREATE TABLE IF NOT EXISTS task_runs (task_name TEXT "
                "PRIMARY KEY, last_run TIMESTAMP WITH TIME ZONE)"
            )
        )
        cur.execute(
            (
                "INSERT INTO task_runs (task_name, last_run) VALUES (%s, %s) "
                "ON CONFLICT (task_name) DO UPDATE SET last_run=%s"
            ),
            (
                "generate_province_revenue",
                past,
                past,
            ),
        )
        conn.commit()

    result = run_script(threshold_hours=1)
    assert result.returncode != 0, "stale task should cause nonzero exit code"
    assert "exceeding threshold" in result.stdout
