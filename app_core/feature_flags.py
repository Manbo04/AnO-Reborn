"""Feature flags and kill switch (change pipeline gate 5, docs/CHANGE_PIPELINE.md).

Usage in game code::

    from app_core.feature_flags import is_on
    if is_on("upkeep_v3", user_id):
        ...new behaviour...
    else:
        ...old behaviour...

Rules:
* ``enabled`` is the master switch. Off means off for every nation.
* ``rollout_percent`` picks a stable slice of nations (hash of flag key + user id), so the
  same nation stays in or out of the canary across ticks.
* Fail safe: if the database cannot be read, the last good value is used, and if there is
  none, the caller's ``default`` (the old behaviour) is used. A flag read never raises.
* Each process caches the table for ``CACHE_SECONDS``, so a flip reaches web and worker
  processes within that time.
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

CACHE_SECONDS = 15
KEY_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

_lock = threading.Lock()
_cache: Dict[str, dict] = {}
_cache_at = 0.0
_cache_ok = False


def valid_key(key: str) -> bool:
    return bool(key) and bool(KEY_RE.match(key))


def bucket(key: str, user_id) -> int:
    """Stable 0-99 slice for this flag and nation."""
    digest = hashlib.sha256(f"{key}:{user_id}".encode()).digest()
    return int.from_bytes(digest[:4], "big") % 100


def _load_all() -> Dict[str, dict]:
    from database import get_db_cursor

    with get_db_cursor(read_only=True) as cur:
        cur.execute(
            "SELECT key, enabled, rollout_percent, description, rollback_trigger, "
            "updated_by, updated_at FROM feature_flags"
        )
        rows = cur.fetchall()
    return {
        r[0]: {
            "key": r[0],
            "enabled": bool(r[1]),
            "rollout_percent": int(r[2]),
            "description": r[3] or "",
            "rollback_trigger": r[4] or "",
            "updated_by": r[5],
            "updated_at": r[6],
        }
        for r in rows
    }


def _flags(force: bool = False) -> Dict[str, dict]:
    global _cache, _cache_at, _cache_ok
    now = time.monotonic()
    with _lock:
        if not force and _cache_ok and now - _cache_at < CACHE_SECONDS:
            return _cache
    try:
        fresh = _load_all()
    except Exception as exc:  # never let a flag read break the game
        logger.warning("feature_flags: read failed, using last good value: %s", exc)
        with _lock:
            _cache_at = now - CACHE_SECONDS + 5  # retry in 5s, not on every call
            return _cache
    with _lock:
        _cache, _cache_at, _cache_ok = fresh, now, True
        return _cache


def invalidate() -> None:
    global _cache_at, _cache_ok
    with _lock:
        _cache_at, _cache_ok = 0.0, False


def decide(flag: Optional[dict], key: str, user_id, default: bool) -> bool:
    """Pure decision rule, kept separate so it is easy to test."""
    if flag is None:
        return default
    if not flag["enabled"]:
        return False
    pct = flag["rollout_percent"]
    if pct >= 100:
        return True
    if pct <= 0 or user_id is None:
        return False
    return bucket(key, user_id) < pct


def is_on(key: str, user_id=None, default: bool = False) -> bool:
    return decide(_flags().get(key), key, user_id, default)


def list_flags() -> List[dict]:
    return sorted(_flags(force=True).values(), key=lambda f: f["key"])


def set_flag(
    key: str,
    enabled: bool,
    rollout_percent: int,
    actor: str,
    admin_user_id=None,
    description: Optional[str] = None,
    rollback_trigger: Optional[str] = None,
    create: bool = False,
) -> None:
    """Create or update a flag and write an audit row. Raises ValueError on bad input."""
    from app_core.admin.repositories import AdminRepository
    from database import get_db_cursor

    if not valid_key(key):
        raise ValueError("Flag key must be lowercase letters, digits and underscores (3-64 chars).")
    try:
        pct = int(rollout_percent)
    except (TypeError, ValueError):
        raise ValueError("Rollout percent must be a whole number.")
    if not 0 <= pct <= 100:
        raise ValueError("Rollout percent must be between 0 and 100.")
    description = (description or "").strip()[:300]
    rollback_trigger = (rollback_trigger or "").strip()[:300]

    with get_db_cursor() as cur:
        cur.execute("SELECT enabled, rollout_percent FROM feature_flags WHERE key = %s FOR UPDATE", (key,))
        before = cur.fetchone()
        if before is None and not create:
            raise ValueError("Unknown flag.")
        if before is None:
            if not rollback_trigger:
                raise ValueError("A new flag needs a rollback trigger written down.")
            cur.execute(
                "INSERT INTO feature_flags (key, enabled, rollout_percent, description, "
                "rollback_trigger, updated_by) VALUES (%s, %s, %s, %s, %s, %s)",
                (key, bool(enabled), pct, description, rollback_trigger, actor),
            )
        else:
            cur.execute(
                "UPDATE feature_flags SET enabled = %s, rollout_percent = %s, updated_by = %s, "
                "updated_at = now() WHERE key = %s",
                (bool(enabled), pct, actor, key),
            )
        AdminRepository.log_admin_action(
            cur,
            actor,
            "feature_flag_set",
            admin_user_id,
            {
                "key": key,
                "before": None if before is None else {"enabled": before[0], "percent": before[1]},
                "after": {"enabled": bool(enabled), "percent": pct},
            },
        )
    invalidate()
