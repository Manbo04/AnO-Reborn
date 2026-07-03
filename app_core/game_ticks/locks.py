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

_redis_pool = None


_delete_lock_lua = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


_redis_pool = None



def try_pg_advisory_lock(conn, lock_id: int, label: str) -> bool:
    """Attempt a transaction-level advisory lock.

    Uses pg_try_advisory_xact_lock so the lock is automatically released
    when the transaction ends (COMMIT or ROLLBACK), eliminating the risk
    of stale session-level locks blocking all future runs if a task
    crashes without explicit cleanup.
    """
    try:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_xact_lock(%s)", (lock_id,))
        row = cur.fetchone()
        if not row:
            # In some test fakes, fetchone() may return None; allow tasks
            # to proceed while logging a warning.
            print(
                f"{label}: advisory lock query returned no rows " "- proceeding anyway"
            )
            return True
        acquired = row[0]
        if not acquired:
            print(f"{label}: another run is already in progress, " "skipping")
        return acquired
    except Exception as e:
        print(f"{label}: failed to acquire advisory lock: {e}")
        return False




def release_pg_advisory_lock(conn, lock_id: int):
    """No-op kept for backward compatibility.

    Transaction-level advisory locks (pg_try_advisory_xact_lock) are
    released automatically on COMMIT / ROLLBACK, so explicit unlocks
    are no longer needed.  Callers that still invoke this function
    will simply succeed harmlessly.
    """


def _get_redis_client():
    global _redis_pool
    if _redis_pool is None:
        import urllib.parse
        url = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
        if not url:
            return None
        parsed = urllib.parse.urlparse(url)
        _redis_pool = redis.ConnectionPool(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password,
            max_connections=10
        )
    return redis.Redis(connection_pool=_redis_pool)



def leader_only(ttl_seconds=60, key_prefix="task_lock"):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            if redis is None:
                return fn(*args, **kwargs)
            try:
                r = _get_redis_client()
                if not r:
                    return fn(*args, **kwargs)
                
                key = f"{key_prefix}:{fn.__name__}"
                import uuid
                lock_id = str(uuid.uuid4())
                
                got = r.set(key, lock_id, nx=True, ex=ttl_seconds)
                if not got:
                    print(f"{fn.__name__}: skipped (leader lock not acquired)")
                    return
                try:
                    return fn(*args, **kwargs)
                finally:
                    try:
                        r.eval(_delete_lock_lua, 1, key, lock_id)
                    except Exception:
                        pass
            except Exception as e:
                print(f"leader_only decorator error for {fn.__name__}: {e}")
                return fn(*args, **kwargs)

        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper

    return decorator


