"""Live guardrail numbers for the admin dashboard.

Uses the app's own read-only cursor (not BALANCE_DATABASE_URL), runs the harness SELECT, and
caches for LIVE_CACHE_SECONDS. A failure returns an error string, never raises into the page.
"""
from __future__ import annotations

import datetime as dt
import threading
import time
from typing import Optional, Tuple

from . import guardrails, snapshot
from .metrics import summarise

LIVE_CACHE_SECONDS = 300
_lock = threading.Lock()
_cached: Optional[Tuple[float, dict]] = None


def current_summary(force: bool = False) -> Tuple[Optional[dict], Optional[str]]:
    """Return (summary, error). Summary carries 'as_of' (UTC ISO string)."""
    global _cached
    now = time.monotonic()
    with _lock:
        if not force and _cached and now - _cached[0] < LIVE_CACHE_SECONDS:
            return _cached[1], None
    try:
        from database import get_db_cursor

        snapshot.assert_select_only(snapshot.SNAPSHOT_SQL)
        with get_db_cursor(read_only=True) as cur:
            cur.execute(snapshot.SNAPSHOT_SQL)
            rows = cur.fetchall()
        when = dt.datetime.now(dt.timezone.utc)
        summary = summarise(snapshot.anonymise(rows, when), reference_cost=50_000_000)
        summary["as_of"] = when.strftime("%Y-%m-%d %H:%M UTC")
    except Exception as exc:  # the page must render even if the query fails
        return None, f"Could not read live numbers: {exc}"
    with _lock:
        _cached = (now, summary)
    return summary, None


def thresholds() -> dict:
    return {
        "max_share_net_le_0_rise": guardrails.MAX_SHARE_NET_LE_0_RISE,
        "max_median_net_drop": guardrails.MAX_MEDIAN_NET_DROP,
        "max_new_player_net_drop": guardrails.MAX_NEW_PLAYER_NET_DROP,
        "min_new_player_net": guardrails.MIN_NEW_PLAYER_NET,
    }
