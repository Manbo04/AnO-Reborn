"""Monitor production deployment until it's healthy.

Checks:
 - GET /health returns 200 and body 'ok'
 - POST /signup with test data does not return 500 (ensures signup route is fixed)
 - task_runs last_run for key tasks is recent (<= 20 minutes)

Run locally: PYTHONPATH=. python scripts/monitor_deploy.py
"""

import time
import requests
import os
from datetime import datetime, timezone, timedelta

# Config
BASE_URL = (
    os.environ.get("RAILWAY_SERVICE_WEB_URL")
    or os.environ.get("RAILWAY_PUBLIC_DOMAIN")
    or "https://affairsandorder.com"
)
DB_URL = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")


def check_health():
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=5)
        return r.status_code == 200 and r.text.strip().lower() == "ok"
    except Exception as e:
        print("health check error:", e)
        return False


def check_signup():
    try:
        data = {
            "username": "monitor_test",
            "email": "monitor+test@example.invalid",
            "password": "pw",
            "confirmation": "pw",
            "g-recaptcha-response": "invalid",
            "continent": "1",
        }
        r = requests.post(
            f"{BASE_URL}/signup", data=data, timeout=10, allow_redirects=False
        )
        # we only assert it didn't 500
        return r.status_code != 500
    except Exception as e:
        print("signup check error:", e)
        return False


def check_tasks():
    if not DB_URL:
        print("No DB URL configured; skipping task run check")
        return True
    try:
        from database import get_db_connection

        with get_db_connection() as conn:
            cur = conn.cursor()
            query = (
                "SELECT task_name, last_run FROM task_runs "
                "WHERE task_name IN ('generate_province_revenue', 'tax_income')"
            )
            cur.execute(query)
            rows = cur.fetchall()
            now = datetime.now(timezone.utc)
            threshold = now - timedelta(minutes=20)
            for name, last in rows:
                if last is None:
                    print(f"task {name} has never run")
                    return False
                if last < threshold:
                    print(
                        f"task {name} last_run={last} is older"
                        f" than threshold {threshold}"
                    )
                    return False
            return True
    except Exception as e:
        print("task check error:", e)
        return False


def monitor_loop(timeout_minutes=None):
    # Allow overriding via environment variable MONITOR_TIMEOUT_MINUTES
    if timeout_minutes is None:
        try:
            timeout_minutes = int(os.environ.get("MONITOR_TIMEOUT_MINUTES", "30"))
        except Exception:
            timeout_minutes = 30
    deadline = time.time() + timeout_minutes * 60
    while time.time() < deadline:
        healthy = check_health()
        signup_ok = check_signup()
        tasks_ok = check_tasks()
        now_iso = datetime.now(timezone.utc).isoformat()
        print(
            f"health={healthy} signup_ok={signup_ok} tasks_ok={tasks_ok} -- {now_iso}"
        )
        if healthy and signup_ok and tasks_ok:
            print("All checks passed — deployment looks healthy ✅")
            return 0
        time.sleep(15)
    print("Timed out waiting for healthy deployment 🚨")
    return 1


if __name__ == "__main__":
    exit(monitor_loop())
