#!/usr/bin/env python3
"""Enqueue critical Celery tasks when beat scheduling has stalled (web boot safety net).

Beat can exit 0 on deploy and stop scheduling; workers may still be Online. This
script checks task_runs freshness and sends tasks to the Redis queue at most once
per NUDGE_COOLDOWN_SECONDS (Redis lock).

Does NOT replace a healthy beat service — redeploy beat + celery-worker on Railway.

Usage (automatic from scripts/start_production.sh):
    DATABASE_URL=... REDIS_URL=... python3 scripts/nudge_stale_economy_tasks.py
"""

from __future__ import annotations

import os
import sys
import urllib.parse

from dotenv import load_dotenv

load_dotenv()

CRITICAL = (
    "generate_province_revenue",
    "global_tick",
    "tax_income",
)

TASK_SEND_MAP = {
    "generate_province_revenue": "tasks.task_generate_province_revenue",
    "global_tick": "tasks.task_global_tick",
    "tax_income": "tasks.task_tax_income",
}

DEFAULT_STALE_SECONDS = {
    "generate_province_revenue": int(
        os.getenv("READY_MAX_REVENUE_AGE_SECONDS", "7200")
    ),
    "global_tick": int(os.getenv("GLOBAL_TICK_STALE_SECONDS", "1800")),
    "tax_income": int(os.getenv("TAX_INCOME_STALE_SECONDS", "7200")),
}

NUDGE_LOCK_KEY = os.getenv("WEB_ECONOMY_NUDGE_LOCK_KEY", "web:economy_nudge:v1")
NUDGE_COOLDOWN = int(os.getenv("WEB_ECONOMY_NUDGE_COOLDOWN_SECONDS", "900"))


def _redis_client():
    import redis

    url = os.getenv("REDIS_URL") or os.getenv("REDIS_PUBLIC_URL")
    if not url:
        return None
    p = urllib.parse.urlparse(url)
    return redis.Redis(
        host=p.hostname,
        port=p.port or 6379,
        password=p.password,
        decode_responses=True,
    )


def _task_ages_seconds(cur) -> dict[str, float | None]:
    cur.execute(
        """
        SELECT task_name,
               EXTRACT(EPOCH FROM (now() - last_run)) AS age_seconds
        FROM task_runs
        WHERE task_name = ANY(%s)
        """,
        (list(CRITICAL),),
    )
    out: dict[str, float | None] = {name: None for name in CRITICAL}
    for name, age in cur.fetchall():
        out[name] = float(age) if age is not None else None
    return out


def main() -> int:
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if not db_url:
        print("[nudge] SKIP: no DATABASE_URL")
        return 0

    import psycopg2

    stale_tasks: list[str] = []
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        ages = _task_ages_seconds(cur)
        cur.close()
        conn.close()
    except Exception as exc:
        print(f"[nudge] WARN: could not read task_runs: {exc}")
        return 0

    for name, age in ages.items():
        limit = DEFAULT_STALE_SECONDS.get(name, 7200)
        if age is None or age > limit:
            stale_tasks.append(name)
            print(
                f"[nudge] stale {name}: age_seconds={age} threshold={limit}"
            )

    if not stale_tasks:
        print("[nudge] economy tasks fresh — nothing to enqueue")
        return 0

    r = _redis_client()
    if r is None:
        print("[nudge] WARN: no REDIS_URL — cannot rate-limit nudge")
        return 0

    try:
        if not r.set(NUDGE_LOCK_KEY, "1", nx=True, ex=NUDGE_COOLDOWN):
            print(f"[nudge] SKIP: lock {NUDGE_LOCK_KEY} held (cooldown {NUDGE_COOLDOWN}s)")
            return 0
    except Exception as exc:
        print(f"[nudge] WARN: redis lock failed: {exc}")
        return 0

    # Clear beat leader lock so beat service can re-acquire on next restart
    try:
        for key in (
            "beat:leader",
            os.getenv("BEAT_LEADER_LOCK_KEY", "beat:leader"),
        ):
            if key:
                r.delete(key)
    except Exception:
        pass

    sent = []
    try:
        from tasks import celery as celery_app

        for name in stale_tasks:
            task_path = TASK_SEND_MAP.get(name)
            if not task_path:
                continue
            celery_app.send_task(task_path)
            sent.append(name)
    except Exception as exc:
        print(f"[nudge] ERROR sending celery tasks: {exc}")
        try:
            r.delete(NUDGE_LOCK_KEY)
        except Exception:
            pass
        return 1

    print(f"[nudge] enqueued: {', '.join(sent) or 'none'}")
    print("[nudge] ensure celery-worker service is Online on Railway")
    return 0


if __name__ == "__main__":
    sys.exit(main())
