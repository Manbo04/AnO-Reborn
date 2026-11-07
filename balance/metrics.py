"""Pure metrics over a list of nations. No database, no network."""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Dict, Iterable, List, Optional

NEW_PLAYER_MAX_DAYS = 7
ACTIVE_MAX_DAYS = 7
WHALE_TOP_FRACTION = 0.05


@dataclass(frozen=True)
class Nation:
    """One anonymised nation. All money is gold; net_per_hour is signed gold per hour."""

    idx: int
    gold: int
    net_per_hour: float
    age_days: float
    idle_days: float
    is_ai: bool = False
    military_gold_value: int = 0  # gold value of units, used by upkeep scenarios
    loan_interest_per_hour: float = 0.0  # already subtracted from net_per_hour; kept for reporting

    @property
    def active(self) -> bool:
        return (not self.is_ai) and self.idle_days <= ACTIVE_MAX_DAYS


def median(vals) -> Optional[float]:
    """Median without the stdlib statistics module (the repo root has its own statistics.py,
    which shadows it when running from the repo root)."""
    s = sorted(vals)
    if not s:
        return None
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def active_humans(nations: Iterable[Nation]) -> List[Nation]:
    return [n for n in nations if n.active]


def mi_hour(nations: Iterable[Nation]) -> Optional[float]:
    """Gold per hour of the median active human nation. The unit all targets are written in."""
    vals = [n.net_per_hour for n in active_humans(nations)]
    return median(vals)


def to_mi_hours(gold_amount: float, mi: float) -> float:
    """Express a gold amount in MI-hours (hours of median income)."""
    return gold_amount / mi if mi and mi > 0 else float("inf")


def hours_to_afford(nation: Nation, cost: float) -> float:
    """Hours until this nation can pay cost, from its own treasury and net income."""
    if nation.gold >= cost:
        return 0.0
    if nation.net_per_hour <= 0:
        return float("inf")
    return (cost - nation.gold) / nation.net_per_hour


_median = median


def archetypes(nations: List[Nation]) -> Dict[str, List[Nation]]:
    active = active_humans(nations)
    new = [n for n in active if n.age_days <= NEW_PLAYER_MAX_DAYS]
    by_gold = sorted(active, key=lambda n: n.gold, reverse=True)
    k = max(1, int(len(by_gold) * WHALE_TOP_FRACTION)) if by_gold else 0
    return {
        "new": new,
        "median": active,
        "whale": by_gold[:k],
        "ai": [n for n in nations if n.is_ai],
    }


def summarise(nations: List[Nation], reference_cost: Optional[float] = None) -> dict:
    """Numbers for the report and the guardrails."""
    from .economy import money_block

    groups = archetypes(nations)
    active = groups["median"]
    out: dict = {
        "n_total": len(nations),
        "n_active": len(active),
        "mi_hour": mi_hour(nations),
        "share_net_le_0": (sum(1 for n in active if n.net_per_hour <= 0) / len(active)) if active else None,
        "archetypes": {},
        "curve": curve_shape(nations),
        "money": money_block(nations),
        "retention": retention(nations),
    }
    for name in ("new", "median", "whale", "ai"):
        g = groups[name]
        row = {
            "n": len(g),
            "median_net": _median([n.net_per_hour for n in g]),
            "share_net_le_0": (sum(1 for n in g if n.net_per_hour <= 0) / len(g)) if g else None,
        }
        if reference_cost is not None:
            row["median_hours_to_afford"] = _median([hours_to_afford(n, reference_cost) for n in g])
        out["archetypes"][name] = row
    return out


def gini(values) -> Optional[float]:
    """Gini coefficient (0 equal, 1 one nation has everything). None if there is nothing to measure."""
    v = sorted(max(0.0, float(x)) for x in values)
    n, total = len(v), sum(v)
    if n < 2 or total <= 0:
        return None
    weighted = sum((i + 1) * x for i, x in enumerate(v))
    return (2 * weighted) / (n * total) - (n + 1) / n


def loglog_slope(xs, ys) -> Optional[float]:
    """Least-squares slope of log(y) on log(x), positive pairs only. Needs 10 points.
    For income vs wealth: below 1 means income grows slower than wealth (tapering curve), above 1
    means richer nations earn proportionally more (snowball)."""
    pts = [(math.log(x), math.log(y)) for x, y in zip(xs, ys) if x > 0 and y > 0]
    if len(pts) < 10:
        return None
    mx = sum(p[0] for p in pts) / len(pts)
    my = sum(p[1] for p in pts) / len(pts)
    var = sum((p[0] - mx) ** 2 for p in pts)
    if var == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in pts) / var


TOP_DECILE = 0.10
HIBERNATION_IDLE_DAYS = 2.0


def curve_shape(nations: List[Nation]) -> dict:
    """Progression-curve and staleness indicators over active human nations.
    * gini_income: inequality of positive net income.
    * income_wealth_slope: log-log slope of net income vs gold (see loglog_slope).
    * top_decile_income_share: share of all positive income earned by the top 10% of earners.
    * top_decile_idle_share: share of the richest 10% (by gold) idle for more than 2 days. A rising
      value means late players are waiting with nothing to do (hibernation).
    Active means seen in the last 7 days, so the idle share is measured on that group; nations
    already gone for a week are not counted."""
    active = active_humans(nations)
    incomes = [max(0.0, n.net_per_hour) for n in active]
    total = sum(incomes)
    ranked = sorted(incomes, reverse=True)
    k = max(1, int(len(ranked) * TOP_DECILE)) if ranked else 0
    rich = sorted(active, key=lambda n: n.gold, reverse=True)[: max(1, int(len(active) * TOP_DECILE))] if active else []
    return {
        "gini_income": gini(incomes),
        "income_wealth_slope": loglog_slope([n.gold for n in active], [n.net_per_hour for n in active]),
        "top_decile_income_share": (sum(ranked[:k]) / total) if total > 0 else None,
        "top_decile_idle_share": (sum(1 for n in rich if n.idle_days > HIBERNATION_IDLE_DAYS) / len(rich)) if rich else None,
    }


def with_net(nation: Nation, new_net: float) -> Nation:
    return replace(nation, net_per_hour=new_net)


RETENTION_DAYS = (1, 7, 30)
MAX_PLAUSIBLE_AGE_DAYS = 3650  # anything older is a bad signup date (the database has 1970-01-01 rows)


def retention(nations: Iterable[Nation], days=RETENTION_DAYS) -> dict:
    """Last-seen retention from data that already exists (signup date and last_active).

    A nation counts as retained at day N when its last recorded activity is on or after signup + N days,
    among human nations old enough to have had day N. This is NOT classic "logged in on exactly day N":
    the game keeps only the latest activity time per nation, not a per-day history, and login_events
    covers only a fraction of players. Nations with no activity record are counted as not retained and
    reported separately so the gap is visible.
    """
    humans = [n for n in nations if not n.is_ai and n.age_days < MAX_PLAUSIBLE_AGE_DAYS]
    out: dict = {"basis": "last_active on or after signup + N days (not exact day-N logins)"}
    for d in days:
        matured = [n for n in humans if n.age_days >= d]
        retained = [n for n in matured if n.idle_days < 9999 and (n.age_days - n.idle_days) >= d]
        out[f"d{d}"] = {
            "matured": len(matured),
            "retained": len(retained),
            "rate": (len(retained) / len(matured)) if matured else None,
            "no_activity_record": sum(1 for n in matured if n.idle_days >= 9999),
        }
    return out
