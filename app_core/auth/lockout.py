"""Small shared counter store for auth abuse limits (account lockout, TOTP
replay). Uses Redis when REDIS_URL is set (shared by all gunicorn workers),
otherwise a per-process dict. Every call fails OPEN: a counter outage must
never lock real players out of the site.
"""
from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_mem: dict[str, tuple[int, float]] = {}  # key -> (count, expires_at)
_redis = None
_redis_tried = False


def _client():
    global _redis, _redis_tried
    if _redis_tried:
        return _redis
    _redis_tried = True
    url = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
    if not url:
        return None
    try:
        import redis

        _redis = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
    except Exception:
        logger.exception("lockout: redis unavailable, using in-process counters")
        _redis = None
    return _redis


def _k(scope: str, ident) -> str:
    return f"authguard:{scope}:{ident}"


def incr(scope: str, ident, ttl: int) -> int:
    """Increment and return the counter (TTL starts on the first hit)."""
    key = _k(scope, ident)
    r = _client()
    if r is not None:
        try:
            n = int(r.incr(key))
            if n == 1:
                r.expire(key, ttl)
            return n
        except Exception:
            logger.warning("lockout: redis incr failed", exc_info=True)
    now = time.time()
    with _lock:
        count, exp = _mem.get(key, (0, 0.0))
        if exp < now:
            count, exp = 0, now + ttl
        count += 1
        _mem[key] = (count, exp)
        if len(_mem) > 5000:
            for stale in [k for k, (_, e) in _mem.items() if e < now]:
                _mem.pop(stale, None)
        return count


def get(scope: str, ident) -> int:
    key = _k(scope, ident)
    r = _client()
    if r is not None:
        try:
            v = r.get(key)
            return int(v) if v else 0
        except Exception:
            logger.warning("lockout: redis get failed", exc_info=True)
    with _lock:
        count, exp = _mem.get(key, (0, 0.0))
        return count if exp >= time.time() else 0


def clear(scope: str, ident) -> None:
    key = _k(scope, ident)
    r = _client()
    if r is not None:
        try:
            r.delete(key)
        except Exception:
            logger.warning("lockout: redis delete failed", exc_info=True)
    with _lock:
        _mem.pop(key, None)


def claim_once(scope: str, ident, ttl: int) -> bool:
    """True the first time (scope, ident) is claimed within ttl seconds."""
    return incr(scope, ident, ttl) == 1


# --- policies -------------------------------------------------------------
TWOFA_MAX_FAILURES = 5
TWOFA_WINDOW = 15 * 60
PASSWORD_MAX_FAILURES = 20
PASSWORD_WINDOW = 15 * 60


def twofa_locked(user_id: int) -> bool:
    return get("2fa_fail", user_id) >= TWOFA_MAX_FAILURES


def twofa_record_failure(user_id: int) -> int:
    return incr("2fa_fail", user_id, TWOFA_WINDOW)


def twofa_clear(user_id: int) -> None:
    clear("2fa_fail", user_id)


def password_locked(user_id: int) -> bool:
    return get("pw_fail", user_id) >= PASSWORD_MAX_FAILURES


def password_record_failure(user_id: int) -> int:
    return incr("pw_fail", user_id, PASSWORD_WINDOW)


def password_clear(user_id: int) -> None:
    clear("pw_fail", user_id)
