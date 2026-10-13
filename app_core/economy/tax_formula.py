"""The hourly tax formula, shared by the tax_income tick and every display.

The tick (app_core/game_ticks/taxes.py), calc_ti() and the revenue page
(countries.get_revenue) used to carry their own copies of this math, and the
copies drifted apart several times (fabricated policy bonuses, missing food
penalty, missing demographic weighting). Change the formula here only.
"""

import math

import variables
from app_core.economy.consumer_goods import (
    allocate_consumer_goods,
    cg_tax_multiplier,
    province_cg_need,
)


def has_demographic_data(provinces):
    """provinces: iterable of (population, land, pop_children, pop_working, pop_elderly)."""
    return all(p[2] is not None and p[3] is not None and p[4] is not None for p in provinces)


def province_tax_base(population, land, pc, pw, pe, demographic):
    """Pre-multiplier tax income of one province."""
    land_multiplier = min((land - 1) * variables.DEFAULT_LAND_TAX_MULTIPLIER, 1)
    base = variables.DEFAULT_TAX_INCOME
    multiplier = base + (base * land_multiplier)
    if variables.FEATURE_DEMOGRAPHIC_TAX and demographic:
        taxable = (
            (pw or 0) * variables.DEMO_TAX_MULTIPLIER["pop_working"]
            + (pc or 0) * variables.DEMO_TAX_MULTIPLIER["pop_children"]
            + (pe or 0) * variables.DEMO_TAX_MULTIPLIER["pop_elderly"]
        )
    else:
        taxable = population
    return multiplier * taxable


def food_tax_multiplier(provinces, effective_rations):
    """Rations shortage penalty; small new nations get a grace period."""
    total_population = sum(p[0] for p in provinces)
    needed = max(int(total_population // variables.RATIONS_PER), 1)
    rcp = min(0.0, (effective_rations / needed) - 1.0)
    if len(provinces) <= 1 and sum(p[1] for p in provinces) <= 20:
        return 1.0
    return 1.0 + (rcp * (1.0 - variables.NO_FOOD_TAX_MULTIPLIER))


def compute_tax_income(
    provinces, consumer_goods, cg_caps, healthcare, effective_rations=None, tax_multiplier=1.0
):
    """Gross hourly tax income before coalition tax.

    provinces: list of (population, land, pop_children, pop_working, pop_elderly)
    cg_caps: per-province retail capacity, aligned with provinces
    effective_rations: rations that can reach people; None skips the food penalty
    tax_multiplier: product of active directive boosts (app_core/directives)

    Returns dict(income=int, removed_consumer_goods=int, cg_delivered=float).
    """
    if not provinces:
        return {"income": 0, "removed_consumer_goods": 0, "cg_delivered": 0.0}

    demographic = has_demographic_data(provinces)
    incomes = [province_tax_base(*p, demographic) for p in provinces]
    needs = [province_cg_need(p[0], p[2], p[3], p[4], healthcare, demographic) for p in provinces]

    removed = 0
    delivered = 0.0
    if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION:
        alloc = allocate_consumer_goods(needs, cg_caps, consumer_goods)
        income = sum(inc * cg_tax_multiplier(cov) for inc, cov in zip(incomes, alloc["coverage"]))
        removed = alloc["consumed"]
        delivered = sum(alloc["local"]) + sum(alloc["remote"])
    else:
        income = sum(incomes)
        max_cg = math.ceil(sum(needs))
        if consumer_goods != 0 and max_cg != 0:
            if max_cg <= consumer_goods:
                removed = max_cg
                income *= variables.CONSUMER_GOODS_TAX_MULTIPLIER
            else:
                income *= 1 + (0.5 * (consumer_goods / max_cg))
                removed = int(consumer_goods)
        delivered = removed

    if effective_rations is not None:
        income *= food_tax_multiplier(provinces, effective_rations)

    income *= tax_multiplier

    return {
        "income": int(math.floor(income)),
        "removed_consumer_goods": removed,
        "cg_delivered": delivered,
    }
