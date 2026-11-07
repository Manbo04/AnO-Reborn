"""Pure metrics over a list of nations. No database, no network."""
from __future__ import annotations

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
    groups = archetypes(nations)
    active = groups["median"]
    out: dict = {
        "n_total": len(nations),
        "n_active": len(active),
        "mi_hour": mi_hour(nations),
        "share_net_le_0": (sum(1 for n in active if n.net_per_hour <= 0) / len(active)) if active else None,
        "archetypes": {},
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


def with_net(nation: Nation, new_net: float) -> Nation:
    return replace(nation, net_per_hour=new_net)
