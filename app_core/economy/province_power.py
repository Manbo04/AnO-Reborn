"""Per-province power status for a whole nation in one batch (3 queries total).

Shared by Mass Purchase and the nation overview so both show the same
"powered / blackout" answer as the province page (pe.province_energy).
"""

from database import get_request_cursor
from app_core.economy import province_energy as pe


def nation_province_power(user_id: int, provinces: list) -> dict:
    """Return {province_id: province_energy() result} for ``provinces``.

    ``provinces`` is a list of dicts with at least ``id`` and ``productivity``.
    """
    import variables
    from app_core.economy.tick_order import tax_due_before_next_upkeep, upkeep_budget

    if not provinces:
        return {}

    with get_request_cursor() as db:
        energy_names = tuple(variables.ENERGY_CONSUMERS + variables.ENERGY_UNITS)
        db.execute(
            """
            SELECT ub.province_id, bd.name, ub.quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s AND bd.name IN %s
            """,
            (user_id, energy_names),
        )
        units_by_province = {}
        for r in db.fetchall():
            pid, name, qty = (r["province_id"], r["name"], r["quantity"]) if hasattr(r, "get") else r
            units_by_province.setdefault(pid, {})[name] = qty or 0

        db.execute(
            """
            SELECT td.name FROM user_tech ut
            JOIN tech_dictionary td ON td.tech_id = ut.tech_id
            WHERE ut.user_id = %s AND ut.is_unlocked = TRUE
              AND td.name IN ('better_engineering', 'electric_arc_furnace')
            """,
            (user_id,),
        )
        techs = {(r["name"] if hasattr(r, "get") else r[0]) for r in db.fetchall()}
        upgrades = {
            "betterengineering": "better_engineering" in techs,
            "electricarcfurnace": "electric_arc_furnace" in techs,
        }

        db.execute(
            """
            SELECT rd.name, ue.quantity FROM user_economy ue
            JOIN resource_dictionary rd ON rd.resource_id = ue.resource_id
            WHERE ue.user_id = %s AND rd.name IN ('coal', 'oil', 'uranium')
            """,
            (user_id,),
        )
        economy_values = {
            (r["name"] if hasattr(r, "get") else r[0]): (r["quantity"] if hasattr(r, "get") else r[1])
            for r in db.fetchall()
        }
        db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
        gold_row = db.fetchone()
        national_gold = ((gold_row["gold"] if hasattr(gold_row, "get") else gold_row[0]) or 0) if gold_row else 0
        efficiency = pe.national_efficiency_multiplier(db, user_id)

    next_tax = None
    result = {}
    for province in provinces:
        units = units_by_province.get(province["id"], {})
        gold_budget = national_gold
        if pe.producer_upkeep(units) > national_gold and tax_due_before_next_upkeep():
            try:
                if next_tax is None:
                    from countries import get_revenue

                    next_tax = get_revenue(user_id).get("next_tax_income", 0) or 0
                gold_budget = upkeep_budget(national_gold, next_tax)
            except Exception:
                gold_budget = national_gold
        result[province["id"]] = pe.province_energy(
            units, upgrades, province.get("productivity"), efficiency,
            gold_budget, economy_values,
        )
    return result
