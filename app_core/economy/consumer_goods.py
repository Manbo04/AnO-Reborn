"""Per-province consumer-goods distribution.

Consumer goods (CG) are distributed per province: a province's own retail
buildings (food banks, gas stations, general stores, malls, distribution
centers) serve that province's demand at full effect. Retail capacity left
over after a province serves itself is shipped to provinces that are short,
but long-distance delivery only counts at ``variables.REMOTE_CG_EFFICIENCY``
(the goods are still consumed in full -- the rest is lost to transport).
Player suggestion 2026-09-25: "a mall in my capital shouldn't serve a
frontier province".

This is the single implementation shared by the hourly tax tick
(``app_core.game_ticks.taxes``), the tax projection on the country/revenue
page (``countries.py``) and the province page status card, so the three
can't drift apart the way the old duplicated nation-wide formulas did.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence

import variables

# Buildings that distribute consumer goods (capacity per building lives in
# variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING).
CG_DISTRIBUTION_BUILDINGS: tuple[str, ...] = tuple(
    variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING.keys()
)


def province_cg_need(
    population: float,
    pop_children: float | None,
    pop_working: float | None,
    pop_elderly: float | None,
    universal_healthcare: bool,
    has_demographic_data: bool,
) -> float:
    """Hourly CG demand of one province (same formula the tax tick always used)."""
    if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION and has_demographic_data:
        elderly_mult = (
            variables.POLICY_HEALTHCARE_ELDERLY_CG_MULTIPLIER
            if universal_healthcare
            else 1.0
        )
        rates = variables.DEMO_CONSUMER_GOODS_CONSUMPTION
        return (
            (pop_working or 0) * rates["pop_working"]
            + (pop_children or 0) * rates["pop_children"]
            + (pop_elderly or 0) * rates["pop_elderly"] * elderly_mult
        )
    return float(math.ceil((population or 0) / variables.CONSUMER_GOODS_PER))


def province_cg_capacity(building_qty: Mapping[str, int]) -> float:
    """CG distribution capacity of one province from its building counts."""
    caps = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING
    return float(
        sum((building_qty.get(name, 0) or 0) * cap for name, cap in caps.items())
    )


def allocate_consumer_goods(
    needs: Sequence[float], capacities: Sequence[float], stockpile: float
) -> dict:
    """Split a nation's CG stockpile across its provinces.

    Returns ``{"coverage": [...], "consumed": int, "local": [...],
    "remote": [...]}`` where ``coverage[i]`` is the effective share (0..1) of
    province i's demand that was met -- local deliveries count fully, remote
    deliveries count at REMOTE_CG_EFFICIENCY. ``consumed`` is how many CG
    leave the stockpile (remote deliveries are consumed in full).
    """
    n = len(needs)
    local = [min(max(needs[i], 0.0), max(capacities[i], 0.0)) for i in range(n)]
    unmet = [max(needs[i], 0.0) - local[i] for i in range(n)]
    spare = sum(max(capacities[i], 0.0) - local[i] for i in range(n))
    total_unmet = sum(unmet)
    ratio = min(1.0, spare / total_unmet) if total_unmet > 0 else 0.0
    remote = [u * ratio for u in unmet]

    deliverable = sum(local) + sum(remote)
    if deliverable <= 0:
        return {"coverage": [0.0] * n, "consumed": 0, "local": local, "remote": remote}

    stock = max(float(stockpile or 0), 0.0)
    supply = min(1.0, stock / deliverable)
    eff = variables.REMOTE_CG_EFFICIENCY
    coverage = [
        (supply * (local[i] + eff * remote[i]) / needs[i]) if needs[i] > 0 else 0.0
        for i in range(n)
    ]
    consumed = int(deliverable) if supply >= 1.0 else int(stock)
    return {
        "coverage": [min(1.0, c) for c in coverage],
        "consumed": consumed,
        "local": local,
        "remote": remote,
    }


def cg_tax_multiplier(coverage: float) -> float:
    """Tax multiplier for a province given its CG coverage (1.0 .. 1.5)."""
    bonus = variables.CONSUMER_GOODS_TAX_MULTIPLIER - 1.0
    return 1.0 + bonus * max(0.0, min(1.0, coverage))


def load_province_cg_capacities(db, province_ids: Iterable[int]) -> dict[int, float]:
    """Bulk-load CG distribution capacity per province (one query)."""
    ids = list(province_ids)
    if not ids:
        return {}
    db.execute(
        """
        SELECT ub.province_id, bd.name, COALESCE(SUM(ub.quantity), 0) AS qty
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.province_id = ANY(%s) AND bd.name = ANY(%s)
        GROUP BY ub.province_id, bd.name
        """,
        (ids, list(CG_DISTRIBUTION_BUILDINGS)),
    )
    per_province: dict[int, dict[str, int]] = {}
    for row in db.fetchall():
        if isinstance(row, dict):
            pid, name, qty = row.get("province_id"), row.get("name"), row.get("qty")
        else:
            pid, name, qty = row[0], row[1], row[2]
        per_province.setdefault(pid, {})[name] = int(qty or 0)
    return {pid: province_cg_capacity(per_province.get(pid, {})) for pid in ids}
