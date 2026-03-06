#!/usr/bin/env python3
"""Acquire a short-lived Redis lock and run celery beat only if lock obtained.

This prevents running multiple beat instances when the Railway environment
scales the "beat" service to multiple replicas. The script will retry acquiring
the lock for up to BEAT_LEADER_LOCK_TTL * 2 seconds (with backoff), which
handles the common deploy race where the old process's lock hasn't expired yet.

Usage on Railway (set as start command for beat service):
  python scripts/run_beat_if_leader.py

Environment variables:
- REDIS_URL (required) - Redis connection URL
- BEAT_LEADER_LOCK_KEY (optional) - Redis key name to use (default: beat:leader)
- BEAT_LEADER_LOCK_TTL (optional) - lock TTL in seconds (default: 60)
"""

import os
import sys
import time
import subprocess
import urllib.parse

try:
    import redis
except Exception as e:
    print("Missing dependency 'redis' - ensure it's in requirements.txt", e)
    sys.exit(2)

REDIS_URL = (
    os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL") or os.getenv("REDIS_URL")
)
if not REDIS_URL:
    print("No REDIS_URL found in environment; exiting to avoid duplicate beat")
    sys.exit(0)

LOCK_KEY = os.getenv("BEAT_LEADER_LOCK_KEY", "beat:leader")
try:
    LOCK_TTL = int(os.getenv("BEAT_LEADER_LOCK_TTL", "60"))
except Exception:
    LOCK_TTL = 60

# Connect to Redis
parsed = urllib.parse.urlparse(REDIS_URL)
redis_kwargs = {}
if parsed.scheme.startswith("redis"):
    redis_kwargs["host"] = parsed.hostname
    redis_kwargs["port"] = parsed.port or 6379
    if parsed.password:
        redis_kwargs["password"] = parsed.password

r = redis.Redis(**redis_kwargs)

# Try to become leader — retry with backoff to survive deploy races where
# the old process's lock hasn't expired yet.
MAX_ACQUIRE_WAIT = LOCK_TTL * 2  # wait up to 2x TTL
RETRY_INTERVAL = 5  # seconds between attempts
got = False
elapsed = 0
while elapsed < MAX_ACQUIRE_WAIT:
    try:
        got = r.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
    except Exception as e:
        print(f"Redis error when trying to acquire lock (retrying): {e}")
    if got:
        break
    print(
        f"Did not acquire beat leader lock; retrying in {RETRY_INTERVAL}s "
        f"({elapsed}/{MAX_ACQUIRE_WAIT}s elapsed)"
    )
    time.sleep(RETRY_INTERVAL)
    elapsed += RETRY_INTERVAL

if not got:
    print(f"Failed to acquire beat leader lock after {MAX_ACQUIRE_WAIT}s; exiting")
    sys.exit(1)

print("Acquired beat leader lock; running celery beat")
# Refresh the lock periodically in a background loop while beat runs
# Use subprocess and periodically extend lock
proc = subprocess.Popen(["celery", "-A", "tasks.celery", "beat", "--loglevel=INFO"])

try:
    while proc.poll() is None:
        try:
            r.expire(LOCK_KEY, LOCK_TTL)
        except Exception:
            pass
        time.sleep(max(1, LOCK_TTL // 3))
except KeyboardInterrupt:
    proc.terminate()
    proc.wait()
finally:
    try:
        # Remove lock on exit
        r.delete(LOCK_KEY)
    except Exception:
        pass

sys.exit(proc.returncode if proc.returncode is not None else 0)
