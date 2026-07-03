from celery import Celery
import psycopg2
import os
import time
import logging
from dotenv import load_dotenv
from attack_scripts import Economy
import math
from celery.schedules import crontab
import variables
import redis

logger = logging.getLogger(__name__)

load_dotenv()
import config  # Parse Railway environment variables  # noqa: E402

# Toggle noisy per-building revenue logs (default off in production)
VERBOSE_REVENUE_LOGS = os.getenv("VERBOSE_REVENUE_LOGS") == "1"

from app_core.celery_schedule import CELERY_BEAT_SCHEDULE, TASK_RUN_THRESHOLDS

# Mapping from normalized building names to produced resource names.
# Used by the global tick economy engine.
# NOTE: BUILDING_PRODUCTION_RESOURCE_MAP was removed.  These buildings are
# now handled exclusively by generate_province_revenue() (hourly) which
# enforces energy, gold upkeep, and input-resource checks.  Having them
# here too caused DOUBLE production and free resources (steel mills
# produced steel without consuming coal/iron, etc.).
BUILDING_PRODUCTION_RESOURCE_MAP = {}


redis_url = config.get_redis_url()
celery = Celery("app", broker=redis_url)
celery.conf.update(
    broker_url=redis_url, result_backend=redis_url, CELERY_BROKER_URL=redis_url
)

celery.conf.update(
    timezone="UTC",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    beat_schedule=CELERY_BEAT_SCHEDULE,
)


# Centralized helper for last_run threshold check

# Maximum 32-bit signed integer to guard against overflow when writing to DB
MAX_INT_32 = 2_147_483_647


# Maximum 32-bit signed integer to guard against overflow when writing to DB
MAX_INT_32 = 2_147_483_647



# Centralized helper for last_run threshold check
def should_skip_task(row, task_name):
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    threshold = TASK_RUN_THRESHOLDS.get(task_name, 90)
    if row and row[0] and (now - row[0]).total_seconds() < threshold:
        print(f"{task_name}: last run too recent, skipping (interval={threshold}s)")
        return True
    return False




def is_task_stale(task_name: str, stale_seconds: int) -> bool:
    """Return True if a task has not run within stale_seconds.

    This is used as a safety net for scheduler drift/failures so critical
    economy tasks can be self-healed by other periodic tasks.
    """
    from database import get_db_connection
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        with get_db_connection() as conn:
            db = conn.cursor()
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS task_runs (
                    task_name TEXT PRIMARY KEY,
                    last_run TIMESTAMP WITH TIME ZONE
                )
                """
            )
            db.execute(
                "SELECT last_run FROM task_runs WHERE task_name=%s",
                (task_name,),
            )
            row = db.fetchone()
            if not row or not row[0]:
                return True
            age_seconds = (now - row[0]).total_seconds()
            return age_seconds > stale_seconds
    except Exception:
        # Fail-open so watchdog callers can attempt a recovery run.
        return True




# Handles exception for an error
def handle_exception(e, task_name=None):
    filename = __file__
    line = e.__traceback__.tb_lineno if e.__traceback__ else "?"
    print("\n-----------------START OF EXCEPTION-------------------")
    print(f"Filename: {filename}")
    print(f"Error: {e}")
    print(f"Line: {line}")
    print("-----------------END OF EXCEPTION---------------------\n")
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(e)
    except Exception:
        pass
    if task_name:
        try:
            from helpers import record_task_metric

            record_task_metric(f"{task_name}_error", 1.0)
        except Exception:
            pass




def log_verbose(message: str):
    """Emit detailed logs only when enabled."""
    if VERBOSE_REVENUE_LOGS:
        print(message)




def _safe_update_productivity(db, province_id, multiplier):
    """Read the current productivity, apply a multiplier and write back while
    clamping to 32-bit signed integer limits. This prevents DB errors when
    intermediate computations overflow Python int ranges expected by downstream
    databases or drivers in tests."""
    db.execute("SELECT productivity FROM provinces WHERE id=%s", (province_id,))
    row = db.fetchone()
    current = row[0] if row and row[0] is not None else 0
    try:
        new_val = int(round(current * multiplier))
    except Exception:
        new_val = int(current)
    if new_val > MAX_INT_32:
        new_val = MAX_INT_32
    db.execute(
        "UPDATE provinces SET productivity=%s WHERE id=%s", (new_val, province_id)
    )




def _run_with_deadlock_retries(fn, label: str, max_retries: int = 3):
    """Run DB-heavy function with retries on Postgres deadlocks.
    Retries on transient errors as well."""
    import random
    from psycopg2 import errors as pg_errors

    attempt = 0
    while True:
        try:
            return fn()
        except pg_errors.DeadlockDetected as e:
            attempt += 1
            if attempt > max_retries:
                print(
                    f"{label}: exceeded deadlock retries ({max_retries}). "
                    f"Last error: {e}"
                )
                raise
            backoff = 0.2 * attempt + random.uniform(0, 0.2)
            print(
                f"{label}: deadlock detected, retrying in {backoff:.2f}s "
                f"(attempt {attempt}/{max_retries})"
            )
            try:
                from database import db_pool
                try:
                    db_pool.close_all()
                except Exception:
                    pass
            except Exception:
                pass
            try:
                time.sleep(backoff)
            except Exception:
                pass
            continue
        except psycopg2.InterfaceError as e:
            # Connection was closed (likely due to forked workers sharing pool).
            # Attempt pool reset then retry once per attempt.
            print(f"{label}: InterfaceError: {e}. Reinitializing pool and retrying.")
            try:
                from database import db_pool

                try:
                    db_pool.close_all()
                except Exception:
                    pass
            except Exception:
                pass
            attempt += 1
            if attempt > max_retries:
                print(
                    f"{label}: exceeded interface error retries ({max_retries}). "
                    f"Last error: {e}"
                )
                raise
            try:
                time.sleep(0.1 * attempt)
            except Exception:
                pass
            continue


