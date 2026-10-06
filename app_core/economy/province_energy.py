"""Per-province electricity status, shared by /province and /mass_purchase.

Mirrors generate_province_revenue(): consumers use 1 energy/hour (EAF steel
mills 2), producers yield base output (+6 per reactor with Better
Engineering) x productivity x workforce efficiency, and only as many
producers run as the nation can pay gold + fuel upkeep for. Mass purchase
used to compare raw building counts instead, so it flagged provinces as
"Blackout" that /province (and the real tick) showed as powered (ieb,
2026-10-06).
"""

import math

import variables


def _val(row, key, idx):
    return row.get(key) if hasattr(row, "get") else row[idx]


def productivity_multiplier(productivity):
    if productivity is None:
        return 1.0
    return 1 + ((productivity - 50) * variables.DEFAULT_PRODUCTIVITY_PRODUCTION_MULTIPLIER)


def national_efficiency_multiplier(db, user_id):
    """Workforce efficiency -- the same jobs-available/jobs-needed ratio the
    real tick uses. National, so compute once per nation."""
    if not variables.FEATURE_PHASE3_WORKFORCE:
        return 1.0
    db.execute(
        """
        SELECT COALESCE(SUM(pop_working), 0) AS total_pop_working,
               COALESCE(SUM(edu_none), 0) AS edu_none,
               COALESCE(SUM(edu_highschool), 0) AS edu_highschool,
               COALESCE(SUM(edu_college), 0) AS edu_college
        FROM provinces WHERE userId = %s
        """,
        (user_id,),
    )
    demo_row = db.fetchone() or {}
    jobs_available = int(
        (_val(demo_row, "edu_none", 1) or 0)
        + (_val(demo_row, "edu_highschool", 2) or 0)
        + (_val(demo_row, "edu_college", 3) or 0)
    ) if demo_row else 0

    db.execute(
        """
        SELECT bd.name, COALESCE(SUM(ub.quantity), 0) AS count
        FROM user_buildings ub
        JOIN building_dictionary bd ON bd.building_id = ub.building_id
        WHERE ub.user_id = %s GROUP BY bd.name
        """,
        (user_id,),
    )
    national_building_counts = {
        _val(r, "name", 0): int(_val(r, "count", 1) or 0) for r in db.fetchall()
    }
    jobs_needed = sum(
        matrix_data.get("worker_count", 0) * national_building_counts.get(bname, 0)
        for bname, matrix_data in variables.BUILDING_EMPLOYMENT_MATRICES.items()
    )
    if jobs_needed > 0:
        employment_ratio = jobs_available / jobs_needed
        return min(1.0, max(variables.PRODUCTION_EFFICIENCY_MIN, employment_ratio))
    return 1.0


def producer_upkeep(units):
    new_infra = variables.NEW_INFRA
    return sum(
        (new_infra.get(p, {}).get("money", 0) or 0) * (units.get(p, 0) or 0)
        for p in variables.ENERGY_UNITS
    )


def province_energy(units, upgrades, productivity, efficiency_multiplier, gold_budget, economy_values):
    """Energy breakdown for one province. ``gold_budget`` is the gold available
    for producer upkeep; ``economy_values`` holds the nation's fuel stocks."""
    consumers = variables.ENERGY_CONSUMERS
    producers = variables.ENERGY_UNITS
    new_infra = variables.NEW_INFRA

    prod_multiplier = productivity_multiplier(productivity)
    production_multiplier = prod_multiplier * efficiency_multiplier

    # Per-building consumption breakdown (each consumer building uses 1
    # energy/hour, except Electric Arc Furnace steel mills which use 2 —
    # matches the real per-unit cost applied in generate_province_revenue()).
    consumption_breakdown = []
    energy_consumption = 0
    for c in consumers:
        qty = units.get(c, 0) or 0
        if qty <= 0:
            continue
        unit_cost = 2 if (c == "steel_mills" and upgrades.get("electricarcfurnace")) else 1
        subtotal = qty * unit_cost
        energy_consumption += subtotal
        consumption_breakdown.append(
            {"name": c, "quantity": qty, "unit_cost": unit_cost, "subtotal": subtotal}
        )
    consumption_breakdown.sort(key=lambda r: r["subtotal"], reverse=True)

    # Per-building production breakdown. Two numbers per producer:
    # theoretical (every built unit assumed to run) and affordable (how
    # many can actually afford their money + fuel upkeep this hour, same
    # gate generate_province_revenue() applies). Real player report:
    # /province showed reactors "producing" full output even when
    # uranium/gold couldn't actually sustain them, because this display
    # never checked affordability -- only the theoretical formula.
    production_breakdown = []
    theoretical_production = 0
    affordable_production = 0
    gold_remaining = gold_budget
    for p in producers:
        qty = units.get(p, 0) or 0
        if qty <= 0:
            continue
        per_unit_energy = new_infra[p]["plus"]["energy"]
        if p == "nuclear_reactors" and upgrades.get("betterengineering"):
            per_unit_energy += 6

        unit_infra = new_infra.get(p, {})
        money_cost_per_unit = unit_infra.get("money", 0) or 0
        fuel_resource = None
        fuel_cost_per_unit = 0
        for res_name, amt in (unit_infra.get("minus", {}) or {}).items():
            if amt > 0:
                fuel_resource = res_name
                fuel_cost_per_unit = amt
                break

        affordable = qty
        limited_by = []
        if abs(production_multiplier - 1.0) > 1e-9:
            # "Each" shows the building's base rate, but production_multiplier
            # (productivity/workforce efficiency) scales the actual total, so
            # Built x Each can look like it doesn't add up to Total without
            # this note. Real player report: geothermal plants "give 5 units"
            # but total showed 4 with no explanation (ticket-0026).
            limited_by.append("productivity")
        if money_cost_per_unit > 0:
            afford_by_money = int(gold_remaining // money_cost_per_unit)
            if afford_by_money < affordable:
                limited_by.append("money")
            affordable = min(affordable, afford_by_money)
        if fuel_resource:
            have_fuel = economy_values.get(fuel_resource, 0) or 0
            afford_by_fuel = int(have_fuel // fuel_cost_per_unit)
            if afford_by_fuel < affordable:
                limited_by.append(fuel_resource)
            affordable = min(affordable, afford_by_fuel)
        affordable = max(0, affordable)
        gold_remaining -= money_cost_per_unit * affordable

        theoretical = math.ceil(qty * per_unit_energy * production_multiplier) if qty else 0
        actual = math.ceil(affordable * per_unit_energy * production_multiplier) if affordable else 0
        theoretical_production += theoretical
        affordable_production += actual
        production_breakdown.append(
            {
                "name": p,
                "quantity": qty,
                "affordable_units": affordable,
                "unit_output": per_unit_energy,
                "theoretical": theoretical,
                "actual": actual,
                "limited_by": limited_by,
                "fuel_resource": fuel_resource,
            }
        )
    production_breakdown.sort(key=lambda r: r["actual"], reverse=True)

    return {
        "consumption": energy_consumption,
        "production": affordable_production,
        "theoretical_production": theoretical_production,
        "consumption_breakdown": consumption_breakdown,
        "production_breakdown": production_breakdown,
        "net": affordable_production - energy_consumption,
        "production_multiplier": production_multiplier,
        "productivity_pct": productivity,
        "productivity_multiplier": prod_multiplier,
        "efficiency_multiplier": efficiency_multiplier,
        "has_power": affordable_production >= energy_consumption,
    }
