#!/usr/bin/env python3
"""Acquire a short-lived Redis lock and run celery beat only if lock obtained.

This prevents running multiple beat instances when the Railway environment
scales the "beat" service to multiple replicas. The script will attempt to set
an ephemeral lock (SET key value NX EX seconds) and will run `celery beat` if
it becomes leader. If it fails to acquire the lock, it exits safely.

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

# Try to become leader
try:
    got = r.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
except Exception as e:
    print("Redis error when trying to acquire lock; exiting:", e)
    sys.exit(0)

if not got:
    print("Did not acquire beat leader lock; exiting")
    sys.exit(0)

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
