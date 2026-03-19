#!/usr/bin/env python3
"""Acquire a short-lived Redis lock and run celery beat only if lock obtained.

This prevents running multiple beat instances when the Railway environment
scales the "beat" service to multiple replicas. The script will retry acquiring
the lock for up to BEAT_LEADER_LOCK_TTL * 2 seconds (with backoff), which
handles the common deploy race where the old process's lock hasn't expired yet.

If celery beat exits unexpectedly, this script will restart it automatically
(up to MAX_RESTARTS times within RESTART_WINDOW seconds) to survive transient
failures like import errors during deploys.

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
    # Exit 1 so Railway restarts us (REDIS_URL might appear later)
    sys.exit(1)

LOCK_KEY = os.getenv("BEAT_LEADER_LOCK_KEY", "beat:leader")
try:
    LOCK_TTL = int(os.getenv("BEAT_LEADER_LOCK_TTL", "60"))
except Exception:
    LOCK_TTL = 60

# Restart limits: max N restarts within a window to avoid infinite loops
MAX_RESTARTS = 5
RESTART_WINDOW = 300  # 5 minutes

# Connect to Redis
parsed = urllib.parse.urlparse(REDIS_URL)
redis_kwargs = {}
if parsed.scheme.startswith("redis"):
    redis_kwargs["host"] = parsed.hostname
    redis_kwargs["port"] = parsed.port or 6379
    if parsed.password:
        redis_kwargs["password"] = parsed.password

r = redis.Redis(**redis_kwargs)


def acquire_lock():
    """Try to acquire the Redis leader lock with retries."""
    max_wait = LOCK_TTL * 2
    retry_interval = 5
    elapsed = 0
    while elapsed < max_wait:
        try:
            got = r.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
        except Exception as e:
            print(f"Redis error acquiring lock (retrying): {e}")
            got = False
        if got:
            return True
        print(
            f"Did not acquire beat leader lock; retrying in {retry_interval}s "
            f"({elapsed}/{max_wait}s elapsed)"
        )
        time.sleep(retry_interval)
        elapsed += retry_interval
    return False


def run_beat():
    """Run celery beat and keep the Redis lock refreshed."""
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
        return -1
    return proc.returncode


# --- Main loop: acquire lock, run beat, restart on failure ---

if not acquire_lock():
    print(f"Failed to acquire beat leader lock after {LOCK_TTL * 2}s")
    sys.exit(1)

print("Acquired beat leader lock; starting celery beat")

restart_times = []
while True:
    rc = run_beat()
    now = time.time()

    if rc == -1:
        # KeyboardInterrupt / SIGTERM — clean exit
        print("Beat stopped by signal; exiting")
        break

    # Beat exited unexpectedly
    print(f"celery beat exited with code {rc}; checking restart limits")

    # Track restart timestamps within the window
    restart_times = [t for t in restart_times if now - t < RESTART_WINDOW]
    if len(restart_times) >= MAX_RESTARTS:
        print(
            f"Beat restarted {MAX_RESTARTS} times in {RESTART_WINDOW}s; "
            f"giving up (exit 1 for Railway restart)"
        )
        break

    restart_times.append(now)
    wait = 5 * len(restart_times)  # backoff: 5s, 10s, 15s, ...
    print(f"Restarting beat in {wait}s " f"({len(restart_times)}/{MAX_RESTARTS})")
    time.sleep(wait)

    # Re-acquire or refresh lock before restarting
    try:
        r.set(LOCK_KEY, "1", ex=LOCK_TTL)
    except Exception as e:
        print(f"Could not refresh lock before restart: {e}")

# Clean up lock on exit
try:
    r.delete(LOCK_KEY)
except Exception:
    pass

# Always exit 1 so Railway restarts us
sys.exit(1)
