"""Scenarios: functions that turn today's nations into tomorrow's, so a change can be judged
before it ships. Each scenario is pure and returns new Nation objects."""
from __future__ import annotations

from typing import Callable, List

from .metrics import Nation, with_net

Scenario = Callable[[List[Nation]], List[Nation]]


def flat_cost_per_hour(amount: float) -> Scenario:
    """Every nation pays a fixed extra cost each hour (a flat fee)."""
    return lambda ns: [with_net(n, n.net_per_hour - amount) for n in ns]


def income_scale(factor: float) -> Scenario:
    """Scale positive income only (a tax rate change)."""
    return lambda ns: [with_net(n, n.net_per_hour * factor if n.net_per_hour > 0 else n.net_per_hour) for n in ns]


def military_upkeep(rate_per_hour_of_value: float) -> Scenario:
    """Charge upkeep as a fraction of the gold value of each nation's military, per hour."""
    return lambda ns: [with_net(n, n.net_per_hour - n.military_gold_value * rate_per_hour_of_value) for n in ns]


def chain(*scenarios: Scenario) -> Scenario:
    def run(ns: List[Nation]) -> List[Nation]:
        for s in scenarios:
            ns = s(ns)
        return ns

    return run


def parse_scenario(spec: str) -> Scenario:
    """'flat_cost_per_hour:5000' | 'income_scale:0.9' | 'military_upkeep:0.0005', joined by '+'."""
    parts = []
    for piece in spec.split("+"):
        name, _, arg = piece.partition(":")
        name = name.strip()
        if name == "flat_cost_per_hour":
            parts.append(flat_cost_per_hour(float(arg)))
        elif name == "income_scale":
            parts.append(income_scale(float(arg)))
        elif name == "military_upkeep":
            parts.append(military_upkeep(float(arg)))
        else:
            raise ValueError(f"Unknown scenario '{name}'")
    return chain(*parts)
