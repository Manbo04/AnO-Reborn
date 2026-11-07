"""Aggregated daily activity counters, with no user ids stored (flag: activity_counters).

What it records: after a successful player action (a POST on a known route answered 2xx/3xx), one count
for (UTC day, action type, cohort) and one entry in a per-(day, cohort) HyperLogLog sketch that estimates
the number of distinct active users. The sketch holds 1024 one-byte registers made from a keyed hash, so
it cannot be turned back into user ids and stores no ids. Only the counts and the sketches are written.

Cohort (assigned in memory when the action happens, never stored per user):
  new    signed up in the last 7 days
  top10  among the richest 10% (by gold) of humans active in the last 7 days
  other  everyone else

Cost on the hot path: a dict lookup, a flag read (cached 15s) and a keyed hash, all in memory. Database
work happens at most once per FLUSH_SECONDS per web process, in a short separate transaction with a
lock timeout; if it fails the counts stay in memory (bounded) and the request is never affected.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import logging
import math
import os
import threading
import time
from typing import Dict, Iterable, Optional, Tuple

logger = logging.getLogger(__name__)

FLAG_KEY = "activity_counters"
FLUSH_SECONDS = 30
COHORT_REFRESH_SECONDS = 600
MAX_BUFFER_KEYS = 5000
RETENTION_DAYS = 90
HLL_P = 10
HLL_M = 1 << HLL_P
COHORTS = ("new", "top10", "other")

# Route rule (as registered in Flask) -> action type. Only POST routes count; anything else is ignored.
ACTION_RULES: Dict[str, str] = {
    # building and economy actions
    "/build_structure": "build",
    "/api/province/<int:pId>/quick_build": "build",
    "/<way>/<units>/<province_id>": "build",
    "/mass_purchase/buy": "build",
    "/mass_purchase/sell": "build",
    "/military/<way>/<units>": "military",
    # war
    "/declare_war": "declare_war",
    "/war/<int:war_id>/attack": "attack",
    "/war/<int:war_id>/repeat_attack": "attack",
    "/drone_strike": "attack",
    "/cruise_missile_strike": "attack",
    "/nuclear_strike": "attack",
    "/nuclear_strike/<int:war_id>/launch": "attack",
    "/strategic_airstrike": "attack",
    "/api/game_map/attack": "attack",
    "/api/world_map/nodes/<int:node_id>/attack": "attack",
    "/send_peace_offer/<int:war_id>/<int:enemy_id>": "peace",
    "/war/<int:war_id>/surrender": "peace",
    "/war/<int:war_id>/surrender/respond": "peace",
    "/peace_offers": "peace",
    # trade
    "/buy_offer/<offer_id>": "trade",
    "/sell_offer/<offer_id>": "trade",
    "/post_offer/<offer_type>": "trade",
    "/post_trade_offer/<offer_type>/<offeree_id>": "trade",
    "/accept_trade/<trade_id>": "trade",
    "/currency_market/offer": "trade",
    "/currency_market/accept/<int:offer_id>": "trade",
    # research
    "/start_research": "research",
    "/upgrades_sb/<ttype>/<thing>": "research",
    # diplomacy and coalitions
    "/offer_treaty": "diplomacy",
    "/accept_treaty/<offer_id>": "diplomacy",
    "/establish_coalition": "diplomacy",
    "/join/<coalition_id>": "diplomacy",
    "/coalition_invite/<invite_id>/accept": "diplomacy",
    "/deposit_into_bank/<coalition_id>": "coalition_bank",
    "/request_from_bank/<coalition_id>": "coalition_bank",
    "/coalition/<int:coalition_id>/bank-trades/propose": "coalition_bank",
    "/coalition/bank-trades/<int:trade_id>/accept": "coalition_bank",
    # finance, politics, espionage
    "/loans/take": "finance",
    "/loans/repay": "finance",
    "/bonds/create": "finance",
    "/bonds/<int:bond_id>/fund": "finance",
    "/assembly/propose": "politics",
    "/assembly/vote/<int:proposal_id>": "politics",
    "/spyAmount": "espionage",
    "/spyResult": "espionage",
}

_lock = threading.Lock()
_counts: Dict[Tuple[str, str, str], int] = {}
_sketches: Dict[Tuple[str, str], bytearray] = {}
_last_flush = time.monotonic()
_flush_running = False
_cohorts: Dict[int, str] = {}
_cohorts_at = 0.0
_cohort_refreshing = False


# ---------------------------------------------------------------- sketch
def new_sketch() -> bytearray:
    return bytearray(HLL_M)


def _hash64(day: str, user_id: int) -> int:
    key = (os.environ.get("SECRET_KEY") or "activity-fallback").encode()
    digest = hmac.new(key, f"{day}:{user_id}".encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big")


def sketch_add(reg: bytearray, h: int) -> None:
    idx = h >> (64 - HLL_P)
    rest = h & ((1 << (64 - HLL_P)) - 1)
    rho = (64 - HLL_P) - rest.bit_length() + 1
    if rho > reg[idx]:
        reg[idx] = rho


def sketch_merge(a: bytearray, b: bytes) -> bytearray:
    out = bytearray(a)
    for i in range(min(len(out), len(b))):
        if b[i] > out[i]:
            out[i] = b[i]
    return out


def sketch_estimate(reg: bytes) -> float:
    m = HLL_M
    alpha = 0.7213 / (1 + 1.079 / m)
    raw = alpha * m * m / sum(2.0 ** -r for r in reg)
    zeros = sum(1 for r in reg if r == 0)
    if raw <= 2.5 * m and zeros:
        return m * math.log(m / zeros)
    return raw


# ---------------------------------------------------------------- cohorts
def refresh_cohorts(rows: Iterable, now: Optional[dt.datetime] = None) -> Dict[int, str]:
    """rows: (user_id, signup 'YYYY-MM-DD', gold, last_active) for human nations."""
    now = now or dt.datetime.now(dt.timezone.utc)
    out: Dict[int, str] = {}
    active = []
    for uid, signup, gold, last_active in rows:
        try:
            joined = dt.datetime.strptime(str(signup), "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            age = (now - joined).days
        except ValueError:
            age = 9999
        if age < 7:
            out[uid] = "new"
            continue
        if last_active is not None:
            la = last_active if last_active.tzinfo else last_active.replace(tzinfo=dt.timezone.utc)
            if (now - la).days <= 7:
                active.append((int(gold or 0), uid))
        out[uid] = "other"
    active.sort(reverse=True)
    for _gold, uid in active[: max(1, len(active) // 10)] if active else []:
        out[uid] = "top10"
    return out


def _maybe_refresh_cohorts() -> None:
    global _cohorts, _cohorts_at, _cohort_refreshing
    now = time.monotonic()
    if _cohort_refreshing or (_cohorts and now - _cohorts_at < COHORT_REFRESH_SECONDS):
        return
    _cohort_refreshing = True
    try:
        from database import get_db_connection

        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT u.id, u.date, COALESCE(s.gold, 0), u.last_active FROM users u "
                "LEFT JOIN stats s ON s.id = u.id WHERE u.auth_type IS DISTINCT FROM 'bot'"
            )
            rows = cur.fetchall()
        _cohorts = refresh_cohorts(rows)
        _cohorts_at = now
    except Exception:
        logger.warning("activity cohort refresh failed", exc_info=True)
        _cohorts_at = now - COHORT_REFRESH_SECONDS + 60  # retry in a minute
    finally:
        _cohort_refreshing = False


# ---------------------------------------------------------------- recording
def action_for(method: str, rule: Optional[str], status: int) -> Optional[str]:
    if method != "POST" or not rule or not (200 <= status < 400):
        return None
    return ACTION_RULES.get(rule)


def record(action: str, user_id: int, day: Optional[str] = None, cohort: Optional[str] = None) -> None:
    """Count one action in memory. Never raises."""
    try:
        day = day or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
        cohort = cohort or _cohorts.get(int(user_id), "other")
        h = _hash64(day, int(user_id))
        with _lock:
            key = (day, action, cohort)
            if key in _counts or len(_counts) < MAX_BUFFER_KEYS:
                _counts[key] = _counts.get(key, 0) + 1
            reg = _sketches.get((day, cohort))
            if reg is None:
                reg = _sketches[(day, cohort)] = new_sketch()
            sketch_add(reg, h)
    except Exception:
        logger.debug("activity record failed", exc_info=True)


def _due() -> bool:
    return time.monotonic() - _last_flush >= FLUSH_SECONDS


def _write(counts: Dict[Tuple[str, str, str], int], sketches: Dict[Tuple[str, str], bytes]) -> None:
    """One short transaction: add the counts, merge the sketches, prune old days."""
    from database import get_db_connection
    from psycopg2.extras import execute_values

    with get_db_connection() as conn:
        cur = conn.cursor()
        cur.execute("SET LOCAL lock_timeout = '2s'")
        if counts:
            rows = sorted((d, a, c, n) for (d, a, c), n in counts.items())
            execute_values(
                cur,
                "INSERT INTO activity_daily (day, action, cohort, count) VALUES %s "
                "ON CONFLICT (day, action, cohort) DO UPDATE "
                "SET count = activity_daily.count + EXCLUDED.count",
                rows,
            )
        for (day, cohort), reg in sorted(sketches.items()):
            cur.execute(
                "SELECT hll FROM activity_daily_users WHERE day = %s AND cohort = %s FOR UPDATE",
                (day, cohort),
            )
            row = cur.fetchone()
            merged = sketch_merge(bytearray(reg), bytes(row[0])) if row else bytearray(reg)
            cur.execute(
                "INSERT INTO activity_daily_users (day, cohort, hll) VALUES (%s, %s, %s) "
                "ON CONFLICT (day, cohort) DO UPDATE SET hll = EXCLUDED.hll",
                (day, cohort, bytes(merged)),
            )
        cur.execute(
            "DELETE FROM activity_daily WHERE day < (now() AT TIME ZONE 'UTC')::date - %s",
            (RETENTION_DAYS,),
        )
        cur.execute(
            "DELETE FROM activity_daily_users WHERE day < (now() AT TIME ZONE 'UTC')::date - %s",
            (RETENTION_DAYS,),
        )
        conn.commit()


def flush(force: bool = False) -> bool:
    """Write the buffer to the database. Returns True if something was written."""
    global _last_flush, _flush_running
    with _lock:
        if _flush_running or (not force and not _due()):
            return False
        _flush_running = True
        counts, sketches = dict(_counts), {k: bytes(v) for k, v in _sketches.items()}
        _counts.clear()
        _sketches.clear()
        _last_flush = time.monotonic()
    if not counts and not sketches:
        with _lock:
            _flush_running = False
        return False
    try:
        _write(counts, sketches)
        return True
    except Exception:
        logger.warning("activity flush failed; keeping counts in memory", exc_info=True)
        with _lock:
            for k, n in counts.items():
                if k in _counts or len(_counts) < MAX_BUFFER_KEYS:
                    _counts[k] = _counts.get(k, 0) + n
            for k, reg in sketches.items():
                cur_reg = _sketches.get(k)
                _sketches[k] = sketch_merge(cur_reg, reg) if cur_reg else bytearray(reg)
        return False
    finally:
        with _lock:
            _flush_running = False


def init_activity(app) -> None:
    """Register the after_request hook. Cheap and fully guarded."""

    @app.after_request
    def _count_activity(response):
        try:
            from flask import request, session

            action = action_for(request.method, request.url_rule.rule if request.url_rule else None, response.status_code)
            if action is None:
                return response
            uid = session.get("user_id")
            if not uid:
                return response
            from app_core import feature_flags

            if not feature_flags.is_on(FLAG_KEY, None, False):
                return response
            _maybe_refresh_cohorts()
            record(action, int(uid))
            if _due():
                flush()
        except Exception:
            logger.debug("activity hook failed", exc_info=True)
        return response
