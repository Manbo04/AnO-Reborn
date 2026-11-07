"""What players actually do, from the aggregated activity counters (no user ids anywhere).

Reads activity_daily and activity_daily_users (written by app_core/activity.py behind the activity_counters
flag). Pure functions plus one read-only SELECT each. Until the flag has been on for a while the numbers are
empty: the report says so instead of showing zeros as if they were measurements.
"""
from __future__ import annotations

from typing import Dict, Iterable, List

COUNTS_SQL = """
SELECT day, action, cohort, count
FROM activity_daily
WHERE day > (now() AT TIME ZONE 'UTC')::date - 14
ORDER BY day, action, cohort
"""

USERS_SQL = """
SELECT day, cohort, hll
FROM activity_daily_users
WHERE day > (now() AT TIME ZONE 'UTC')::date - 14
ORDER BY day, cohort
"""


def breakdown(count_rows: Iterable, user_rows: Iterable = ()) -> dict:
    """Per-cohort share of each action, plus daily distinct-active estimates from the sketches."""
    from app_core.activity import sketch_estimate

    by_cohort: Dict[str, Dict[str, int]] = {}
    days = set()
    for day, action, cohort, n in count_rows:
        by_cohort.setdefault(cohort, {})
        by_cohort[cohort][action] = by_cohort[cohort].get(action, 0) + int(n)
        days.add(str(day))
    cohorts = {}
    for cohort, actions in by_cohort.items():
        total = sum(actions.values())
        cohorts[cohort] = {
            "total": total,
            "actions": sorted(
                ({"action": a, "count": n, "share": n / total if total else 0.0} for a, n in actions.items()),
                key=lambda r: -r["count"],
            ),
        }
    distinct: Dict[str, Dict[str, int]] = {}
    for day, cohort, hll in user_rows:
        distinct.setdefault(str(day), {})[cohort] = round(sketch_estimate(bytes(hll)))
        days.add(str(day))
    series = [{"day": d, "by_cohort": distinct.get(d, {}), "total": sum(distinct.get(d, {}).values())} for d in sorted(distinct)]
    return {
        "collecting": not by_cohort,
        "days_with_data": len(days),
        "cohorts": cohorts,
        "distinct_active_by_day": series,
        "note": "Distinct counts are HyperLogLog estimates (about 3% error). The top10 cohort is the richest 10% by gold "
                "among humans active in the last 7 days.",
    }


def fetch(cur) -> dict:
    """Run the read-only SELECTs. A missing table (migration not applied) reports as 'collecting'."""
    from .snapshot import assert_select_only

    assert_select_only(COUNTS_SQL)
    assert_select_only(USERS_SQL)
    cur.execute("SELECT to_regclass('public.activity_daily') IS NOT NULL AND to_regclass('public.activity_daily_users') IS NOT NULL")
    if not cur.fetchone()[0]:
        return {**breakdown([], []), "error": "activity tables not created yet"}
    cur.execute(COUNTS_SQL)
    counts = cur.fetchall()
    cur.execute(USERS_SQL)
    users = cur.fetchall()
    return breakdown(counts, users)
