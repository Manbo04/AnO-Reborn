"""Shared affordability math for one building type's tick.

Extracted out of app_core/game_ticks/revenue.py so the real hourly tick and
the /revenue projection (countries.get_revenue) compute "how many of these
buildings can actually run" from the exact same rule, instead of two
implementations that can drift. That drift is what let refineries/reactors/
silos show full projected output while the real tick produced far less or
nothing, because the projection only ever checked gold -- never local energy
or input-resource stock.

Order matters and mirrors the tick: money first, then energy, then each
input resource in the order the building's `minus` dict defines them. Each
gate can only lower `affordable_units`, never raise it.
"""

from __future__ import annotations

from typing import Dict, List, Tuple


def compute_affordable_units(
    unit_amount: int,
    cost_per_unit: float,
    current_money: float,
    energy_per_unit: float,
    current_energy: float,
    per_unit_minus: Dict[str, float],
    current_resources: Dict[str, float],
) -> Tuple[int, List[str]]:
    """How many of `unit_amount` buildings can run this tick, and why any
    can't. Partial, not all-or-nothing -- matches the real tick's behavior
    of running the affordable fraction rather than zeroing the whole type
    out over a single short resource.

    Returns (affordable_units, issues) where issues lists which gates (a
    subset of "money", "energy", or a resource name) actually constrained
    the result below unit_amount.
    """
    affordable = unit_amount
    issues: List[str] = []

    if cost_per_unit > 0:
        by_money = int(current_money // cost_per_unit)
        if by_money < affordable:
            issues.append("money")
        affordable = min(affordable, by_money)

    if energy_per_unit:
        by_energy = int(current_energy // energy_per_unit)
        if by_energy < affordable:
            issues.append("energy")
        affordable = min(affordable, by_energy)

    for resource, amount_per_unit in per_unit_minus.items():
        if amount_per_unit <= 0:
            continue
        available = current_resources.get(resource, 0)
        by_resource = int(available // amount_per_unit)
        if by_resource < affordable:
            issues.append(resource)
        affordable = min(affordable, by_resource)

    affordable = max(0, affordable)
    return affordable, issues
