"""Read-only snapshot of nations for the harness.

Safety:
* Uses BALANCE_DATABASE_URL only. It never falls back to DATABASE_URL, so a stray shell
  default cannot point it at production by accident.
* Every statement must start with SELECT, and the session is set READ ONLY.
* Output is anonymised: no ids, names, emails or Discord ids leave this module.

net_per_hour comes from nation_revenue_history over the last WINDOW_HOURS and only covers the
gold categories that table records (tax, building_upkeep, coalition_tax, pension_crisis).
It does not include military upkeep, loans or market trades. Treat it as the tax-side
economy, not the full cash flow.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import re
from typing import List

from .metrics import Nation

WINDOW_HOURS = 24

SNAPSHOT_SQL = """
SELECT u.auth_type,
       COALESCE(s.gold, 0),
       u.date,
       u.last_active,
       COALESCE(h.net, 0)
FROM users u
LEFT JOIN stats s ON s.id = u.id
LEFT JOIN (
    SELECT user_id, SUM(amount) AS net
    FROM nation_revenue_history
    WHERE recorded_at > now() - interval '24 hours'
    GROUP BY user_id
) h ON h.user_id = u.id
WHERE NOT COALESCE(u.hidden_from_rankings, FALSE) OR u.auth_type = 'bot'
"""

_SELECT_ONLY = re.compile(r"^\s*SELECT\b", re.I)
_FORBIDDEN = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|COPY|CALL)\b", re.I)


def assert_select_only(sql: str) -> None:
    if not _SELECT_ONLY.match(sql) or _FORBIDDEN.search(sql) or ";" in sql.strip().rstrip(";"):
        raise ValueError("Harness queries must be a single SELECT statement.")


def fetch_nations(dsn: str | None = None, now: dt.datetime | None = None, seed: int = 0) -> List[Nation]:
    dsn = dsn or os.environ.get("BALANCE_DATABASE_URL")
    if not dsn:
        raise RuntimeError("Set BALANCE_DATABASE_URL (a read-only connection). DATABASE_URL is not used on purpose.")
    import psycopg2

    assert_select_only(SNAPSHOT_SQL)
    now = now or dt.datetime.now(dt.timezone.utc)
    conn = psycopg2.connect(dsn)
    try:
        conn.set_session(readonly=True, autocommit=True)
        with conn.cursor() as cur:
            cur.execute(SNAPSHOT_SQL)
            rows = cur.fetchall()
    finally:
        conn.close()
    return anonymise(rows, now, seed)


def anonymise(rows, now: dt.datetime, seed: int = 0) -> List[Nation]:
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    out: List[Nation] = []
    for i, (auth_type, gold, join_date, last_active, net_24h) in enumerate(rows):
        try:
            joined = dt.datetime.strptime(str(join_date), "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
            age = max(0.0, (now - joined).total_seconds() / 86400)
        except ValueError:
            age = 9999.0
        if last_active is None:
            idle = 9999.0
        else:
            la = last_active if last_active.tzinfo else last_active.replace(tzinfo=dt.timezone.utc)
            idle = max(0.0, (now - la).total_seconds() / 86400)
        out.append(
            Nation(
                idx=i,
                gold=int(gold),
                net_per_hour=float(net_24h) / WINDOW_HOURS,
                age_days=age,
                idle_days=idle,
                is_ai=(auth_type == "bot"),
            )
        )
    return out


def save(nations: List[Nation], path: str) -> None:
    data = [
        {"gold": n.gold, "net_per_hour": n.net_per_hour, "age_days": round(n.age_days, 2),
         "idle_days": round(n.idle_days, 2), "is_ai": n.is_ai, "military_gold_value": n.military_gold_value}
        for n in nations
    ]
    with open(path, "w") as f:
        json.dump({"nations": data}, f)


def load(path: str) -> List[Nation]:
    with open(path) as f:
        raw = json.load(f)["nations"]
    return [Nation(idx=i, **row) for i, row in enumerate(raw)]
