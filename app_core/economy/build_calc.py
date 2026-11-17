"""Live numbers for the province page's buy pre-calculator and sticky info bar.

Display only: purchase_building() stays the single authority on what a buy
costs and whether it is allowed. This module reads the SAME cost helper
(get_build_cost) so the preview cannot drift from the charge.
"""
from __future__ import annotations

import logging

import variables
from app_core.economy.building_costs import (
    CITY_UNITS,
    LAND_CITY_PRICING,
    LAND_UNITS,
    apply_policy_gold_discount,
    get_build_cost,
    get_slot_type,
    land_city_purchase_cost,
)
from app_core.economy.building_purchase import _load_policies, get_free_slots

logger = logging.getLogger(__name__)


def _unit_costs(policies) -> dict:
    """{building: {gold, resources, slot, jobs}} for every buyable building."""
    from app_core.economy.ledger_goods import is_hidden

    out = {}
    matrices = variables.BUILDING_EMPLOYMENT_MATRICES
    for key in variables.PROVINCE_UNIT_PRICES:
        if not key.endswith("_price"):
            continue
        name = key[: -len("_price")]
        if is_hidden(name):
            continue
        try:
            cost = get_build_cost(name, policies)
        except Exception:  # pragma: no cover - unknown/odd catalogue entry
            continue
        out[name] = {
            "gold": int(cost["gold"]),
            "resources": {r: int(a) for r, a in (cost["resources"] or {}).items()},
            "slot": get_slot_type(name),
            "jobs": int((matrices.get(name) or {}).get("worker_count", 0) or 0),
        }
    return out


SLOT_UNIT = {"city": "cityCount", "land": "land"}


def _land_mult(db, user_id: int) -> float:
    from app_core.directives.services import active_keys, land_price_multiplier_for

    return land_price_multiplier_for(active_keys(db, user_id))


def slot_cost(db, user_id: int, province_id: int, slot: str, n: int) -> int | None:
    """Exact gold for buying n more city/land slots here (same helper the buy route and Mass
    Purchase use). None if the province is not the user's or the slot type is unknown."""
    unit = SLOT_UNIT.get(slot)
    if not unit:
        return None
    col = "citycount" if slot == "city" else "land"
    db.execute(f"SELECT CAST({col} AS INTEGER) FROM provinces WHERE id=%s AND userId=%s", (province_id, user_id))
    row = db.fetchone()
    if not row:
        return None
    return int(land_city_purchase_cost(unit, int(row[0] or 0), int(n), _load_policies(db, user_id), _land_mult(db, user_id)))


def build_calc_payload(db, user_id: int, province_id: int) -> dict | None:
    """Everything the client needs to preview a purchase in one province.

    Returns None when the province is not the user's (the route answers 404).
    """
    db.execute(
        "SELECT CAST(citycount AS INTEGER), land FROM provinces WHERE id=%s AND userId=%s",
        (province_id, user_id),
    )
    row = db.fetchone()
    if not row:
        return None
    city_total, land_total = int(row[0] or 0), int(row[1] or 0)

    db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
    g = db.fetchone()
    gold = int(g[0] or 0) if g else 0

    db.execute(
        "SELECT rd.name, COALESCE(ue.quantity, 0) FROM user_economy ue "
        "JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id "
        "WHERE ue.user_id = %s",
        (user_id,),
    )
    stock = {r[0]: int(r[1] or 0) for r in db.fetchall()}

    free_city = get_free_slots(db, province_id, "city")
    free_land = get_free_slots(db, province_id, "land")

    db.execute(
        "SELECT bd.name, COALESCE(ub.quantity, 0) FROM user_buildings ub "
        "JOIN building_dictionary bd ON bd.building_id = ub.building_id "
        "WHERE ub.user_id = %s AND ub.province_id = %s",
        (user_id, province_id),
    )
    owned = {r[0]: int(r[1] or 0) for r in db.fetchall()}

    jobs_needed = jobs_available = 0
    try:
        from app_core.game_ticks.population import apply_workforce_hiring_and_debuffs

        wf = apply_workforce_hiring_and_debuffs(user_id) or {}
        jobs_needed = int(wf.get("jobs_needed") or 0)
        jobs_available = int(wf.get("jobs_available") or 0)
    except Exception:
        logger.exception("build_calc workforce lookup failed for %s", user_id)

    try:
        from app_core.game_ticks.energy import energy_info

        power_used, power_total = energy_info(province_id)
    except Exception:
        power_used = power_total = 0

    policies = _load_policies(db, user_id)
    mult = _land_mult(db, user_id)
    slots = {}
    for slot, unit in SLOT_UNIT.items():
        base, inc, cap = LAND_CITY_PRICING[unit]
        slots[slot] = {
            "base": base,
            "inc": inc,
            "cap": cap,
            "owned": city_total if slot == "city" else land_total,
            "factor": apply_policy_gold_discount(unit, 1_000_000, policies) / 1_000_000 * mult,
        }

    return {
        "slots": slots,
        "gold": gold,
        "stock": stock,
        "owned": owned,
        "city": {"total": city_total, "free": free_city, "used": city_total - free_city},
        "land": {"total": land_total, "free": free_land, "used": land_total - free_land},
        "power": {"used": int(power_used or 0), "total": int(power_total or 0)},
        "workforce": {"jobs_needed": jobs_needed, "jobs_available": jobs_available},
        "costs": _unit_costs(policies),
        "min_efficiency": float(getattr(variables, "PRODUCTION_EFFICIENCY_MIN", 0.2)),
    }
