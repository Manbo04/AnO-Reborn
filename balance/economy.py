"""Money supply and faucet/sink reporting. Pure functions plus two read-only SELECTs.

Everything here is read-only. The numbers come from real tick data (nation_revenue_history, stats,
user_loans). What the ledger cannot see is listed in UNLEDGERED so nobody mistakes the report for the
whole economy.
"""
from __future__ import annotations

import datetime as dt
from typing import Dict, Iterable, List, Optional

from .metrics import Nation, median

FLOWS_SQL = """
SELECT (recorded_at AT TIME ZONE 'UTC')::date AS day,
       category,
       SUM(amount) AS total,
       COUNT(DISTINCT user_id) AS nations
FROM nation_revenue_history
WHERE recorded_at > now() - interval '7 days'
GROUP BY 1, 2
ORDER BY 1, 2
"""

# Interest due per hour on active loans. The tick takes min(due, borrower gold), so this is an upper bound.
LOANS_SQL = """
SELECT COUNT(*), COALESCE(SUM(balance * interest_rate), 0)
FROM user_loans
WHERE status = 'active'
"""

# How each ledger category moves the money supply.
#   faucet   creates gold, sink destroys it, transfer only moves it (supply unchanged).
CATEGORY_KIND = {
    "tax": "faucet",
    "building_upkeep": "sink",
    "pension_crisis": "sink",
    "coalition_tax": "transfer",  # goes to the coalition bank, not destroyed
}

# Gold flows that are real but NOT in nation_revenue_history, with the reason each is missing.
UNLEDGERED = [
    ("loan_interest", "sink", "taken from the borrower with no ledger row (app_core/game_ticks/loan_interest.py); "
     "estimated here from user_loans, upper bound"),
    ("market_trades", "transfer", "gold moves between nations in a trade, so supply is unchanged; no ledger row "
     "and no per-nation net can be derived without a trade ledger"),
    ("military_upkeep", "n/a", "paid in resources, not gold (app_core/economy/military_upkeep.py); the gold "
     "version (v2) was reverted in #287"),
    ("one_off_spending", "sink", "building, unit and research purchases spend gold at the time of purchase, "
     "with no ledger row; not an hourly income, so not in net_per_hour"),
    ("gifts_and_admin", "faucet", "event gifts and admin grants credit gold with no ledger row"),
]


def money_block(nations: Iterable[Nation]) -> dict:
    """Total supply, split human/AI, and what a typical active human holds."""
    nations = list(nations)
    humans = [n for n in nations if not n.is_ai]
    active = [n for n in humans if n.active]
    total = sum(n.gold for n in nations)
    ranked = sorted((n.gold for n in active), reverse=True)
    top10 = ranked[: max(1, len(ranked) // 10)] if ranked else []
    return {
        "total_supply": total,
        "human_supply": sum(n.gold for n in humans),
        "ai_supply": sum(n.gold for n in nations if n.is_ai),
        "median_active_gold": median([n.gold for n in active]),
        "top10_share_of_active": (sum(top10) / sum(ranked)) if ranked and sum(ranked) else None,
        "n_active": len(active),
    }


def flow_table(rows: Iterable, loan_interest_per_hour: float = 0.0) -> dict:
    """Faucet-versus-sink series by source and sink type.

    rows: (day, category, total, nations). Returns per-day series plus window totals, with unknown
    categories reported as kind "unclassified" instead of being dropped.
    """
    series: Dict[str, Dict[str, int]] = {}
    totals: Dict[str, int] = {}
    for day, category, total, _nations in rows:
        key = str(day)
        series.setdefault(key, {})[category] = series.setdefault(key, {}).get(category, 0) + int(total)
        totals[category] = totals.get(category, 0) + int(total)
    days = sorted(series)
    out_cats = {}
    faucet = transfer = unclassified = 0
    for cat, amount in sorted(totals.items()):
        kind = CATEGORY_KIND.get(cat, "unclassified")
        out_cats[cat] = {"kind": kind, "total": amount}
        if kind == "faucet":
            faucet += amount
        elif kind == "sink":
            pass  # reported below as "destroyed"
        elif kind == "transfer":
            transfer += amount
        else:
            unclassified += amount
    # a sink is stored as a negative ledger amount; report it as a positive "destroyed" number
    destroyed = -sum(v["total"] for v in out_cats.values() if v["kind"] == "sink")
    loan_window = loan_interest_per_hour * 24 * max(1, len(days))
    return {
        "days": days,
        "series": [{"day": d, **series[d]} for d in days],
        "categories": out_cats,
        "created": faucet,
        "destroyed": destroyed,
        "moved": transfer,
        "unclassified": unclassified,
        "net_supply_change_ledgered": faucet - destroyed,
        "loan_interest_per_hour_inferred": loan_interest_per_hour,
        "net_supply_change_with_loan_interest": faucet - destroyed - loan_window,
        "not_in_ledger": [{"flow": f, "kind": k, "why": why} for f, k, why in UNLEDGERED],
    }


def fetch_flows(cur) -> dict:
    """Run the two read-only SELECTs on an existing (read-only) cursor."""
    from .snapshot import assert_select_only

    assert_select_only(FLOWS_SQL)
    assert_select_only(LOANS_SQL)
    cur.execute(FLOWS_SQL)
    rows = cur.fetchall()
    cur.execute(LOANS_SQL)
    n_loans, per_hour = cur.fetchone()
    table = flow_table(rows, float(per_hour or 0))
    table["active_loans"] = int(n_loans or 0)
    return table
