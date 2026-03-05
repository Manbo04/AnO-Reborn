#!/usr/bin/env python3
"""Master Game Economy & Architecture Audit.

Comprehensive extraction of all economic constants, building data,
demographics, and debuff systems from the Affairs & Order codebase.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import variables  # noqa: E402


def generate_master_audit():
    """Generate complete economic audit report."""
    print("\n" + "=" * 80)
    print("MASTER GAME ECONOMY & ARCHITECTURE AUDIT")
    print("Affairs & Order: Complete Economic Blueprint")
    print("=" * 80)
    print("Generated: 4 March 2026\n")

    # SECTION 1: Global Economy & Land
    print("\n" + "=" * 80)
    print("1. GLOBAL ECONOMY & LAND ACQUISITION")
    print("=" * 80)

    print("\n  BASE TAX GENERATION:")
    print(f"    Per Citizen/Worker: ${variables.DEFAULT_TAX_INCOME} base")
    print(
        "    With Consumer Goods: "
        f"{variables.CONSUMER_GOODS_TAX_MULTIPLIER}x multiplier"
    )
    print(
        f"    Per Land Slot Bonus: "
        f"+{variables.DEFAULT_LAND_TAX_MULTIPLIER * 100}% "
        f"per land slot (capped at 100%)"
    )
    print(
        f"    Without Energy: {variables.NO_ENERGY_TAX_MULTIPLIER}x "
        f"({(1 - variables.NO_ENERGY_TAX_MULTIPLIER) * 100:.0f}% reduction)"
    )
    print(
        f"    Without Food: {variables.NO_FOOD_TAX_MULTIPLIER}x "
        f"({(1 - variables.NO_FOOD_TAX_MULTIPLIER) * 100:.0f}% reduction)"
    )

    print("\n  POPULATION GROWTH:")
    print(f"    Base Max Population: {variables.DEFAULT_MAX_POPULATION:,}")
    print(
        f"    Per City Slot: "
        f"+{variables.CITY_MAX_POPULATION_ADDITION:,} max population"
    )
    print(
        f"    Per Land Slot: "
        f"+{variables.LAND_MAX_POPULATION_ADDITION:,} max population"
    )
    print(
        f"    Happiness Impact: "
        f"{variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER * 100}% "
        f"growth modifier per happiness point"
    )
    print(
        f"    Pollution Impact: "
        f"{variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER * 100}% "
        f"reduction per pollution point"
    )

    print("\n  LAND & PROVINCE ACQUISITION COSTS:")
    print("    New Province: $8,000,000 * (1 + 0.16 * province_count)")
    print("      Example: 1st province = $8M, 2nd = $9.28M, 3rd = $10.56M")
    print("    City Slot: $750,000 base + $50,000 per existing city")
    print("      (Linear scaling: nth city costs base + 50k*n)")
    print("    Land Slot: $520,000 base + $25,000 per existing land")
    print("      (Linear scaling: nth land costs base + 25k*n)")

    print("\n  RESOURCE CONSUMPTION (Legacy):")
    print(f"    Rations: 1 per {variables.RATIONS_PER:,} population")
    print(f"    Consumer Goods: 1 per {variables.CONSUMER_GOODS_PER:,} " f"population")
    print("    (Note: Overridden by demographic system if enabled)")

    # SECTION 2: Demographics
    print("\n\n" + "=" * 80)
    print("2. DEMOGRAPHICS & CONSUMPTION (Phase 2/3)")
    print("=" * 80)

    print("\n  AGING RATES (Per Tick):")
    aging = variables.DEMO_AGING_RATES
    print(
        f"    Elderly Death: "
        f"{aging.get('elderly_death_rate', 0) * 100:.1f}% per tick"
    )
    print(
        f"    Working → Elderly: "
        f"{aging.get('working_to_elderly_rate', 0) * 100:.1f}% per tick"
    )
    print(
        f"    Children → Working: "
        f"{aging.get('children_to_working_rate', 0) * 100:.1f}% per tick"
    )

    print("\n  RATIONS CONSUMPTION (Per Capita Per Tick):")
    rations = variables.DEMO_RATIONS_CONSUMPTION
    print(f"    Working Population: " f"{rations.get('pop_working', 0)} rations/person")
    print(f"    Children: " f"{rations.get('pop_children', 0)} rations/person (+30%)")
    print(f"    Elderly: " f"{rations.get('pop_elderly', 0)} rations/person (-20%)")

    print("\n  CONSUMER GOODS CONSUMPTION (Per Capita Per Tick):")
    cg = variables.DEMO_CONSUMER_GOODS_CONSUMPTION
    print(f"    Working Population: {cg.get('pop_working', 0)} CG/person")
    print(f"    Children: {cg.get('pop_children', 0)} CG/person (+20%)")
    print(f"    Elderly: {cg.get('pop_elderly', 0)} CG/person (2x)")

    # SECTION 3: Complete Building Catalog
    print("\n\n" + "=" * 80)
    print("3. COMPLETE BUILDING CATALOG")
    print("=" * 80)

    prices = variables.PROVINCE_UNIT_PRICES
    infra = variables.NEW_INFRA
    matrices = variables.BUILDING_EMPLOYMENT_MATRICES

    categories = [
        (
            "POWER GENERATION",
            [
                "coal_burners",
                "oil_burners",
                "hydro_dams",
                "nuclear_reactors",
                "solar_fields",
            ],
        ),
        (
            "RETAIL / CONSUMER GOODS",
            [
                "gas_stations",
                "general_stores",
                "farmers_markets",
                "malls",
                "banks",
            ],
        ),
        (
            "PUBLIC WORKS / SERVICES",
            [
                "city_parks",
                "libraries",
                "hospitals",
                "universities",
                "monorails",
            ],
        ),
        (
            "MILITARY INFRASTRUCTURE",
            ["army_bases", "harbours", "aerodomes", "admin_buildings", "silos"],
        ),
        (
            "RESOURCE EXTRACTION",
            [
                "farms",
                "pumpjacks",
                "coal_mines",
                "bauxite_mines",
                "copper_mines",
                "uranium_mines",
                "lead_mines",
                "iron_mines",
                "lumber_mills",
            ],
        ),
        (
            "RESOURCE PROCESSING",
            [
                "component_factories",
                "steel_mills",
                "ammunition_factories",
                "aluminium_refineries",
                "oil_refineries",
            ],
        ),
    ]

    for category_name, buildings in categories:
        print(f"\n  {category_name}:")
        print("  " + "-" * 76)
        for bname in buildings:
            building_data = infra.get(bname, {})

            # Build cost
            price_key = f"{bname}_price"
            resource_key = f"{bname}_resource"
            build_cost = prices.get(price_key, 0)
            build_resources = prices.get(resource_key, {})

            # Gold upkeep per tick
            gold_upkeep = building_data.get("money", 0)

            # Production (plus)
            production = building_data.get("plus", {})

            # Resource consumption (minus)
            consumption = building_data.get("minus", {})

            # Effects
            effects = building_data.get("eff", {})
            neg_effects = building_data.get("effminus", {})

            # Employment
            employment = matrices.get(bname, {})
            workers = employment.get("worker_count", 0)
            edu = employment.get("education", {})

            # Distribution capacity
            dist_cap = 0
            if bname in variables.CONSUMER_GOODS_DISTRIBUTION_BUILDINGS:
                dist_cap = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING
            if bname in variables.RATIONS_DISTRIBUTION_BUILDINGS:
                dist_cap = variables.RATIONS_DISTRIBUTION_PER_BUILDING

            # Print building name
            print(f"\n    {bname.upper().replace('_', ' ')}:")

            # Build cost
            cost_parts = [f"${build_cost:,}"]
            if build_resources:
                res_str = ", ".join(f"{v} {k}" for k, v in build_resources.items())
                cost_parts.append(res_str)
            print(f"      Build Cost: {' + '.join(cost_parts)}")

            # Gold upkeep
            if gold_upkeep > 0:
                print(f"      Gold Upkeep: ${gold_upkeep:,} per tick")

            # Resource consumption
            if consumption:
                cons_str = ", ".join(f"{v} {k}" for k, v in consumption.items())
                print(f"      Consumes: {cons_str} per tick")

            # Production
            if production:
                prod_str = ", ".join(f"+{v} {k}" for k, v in production.items())
                print(f"      Produces: {prod_str} per tick")

            # Distribution capacity
            if dist_cap > 0:
                print(
                    f"      Distribution Cap: {dist_cap:,} "
                    f"population coverage/building"
                )

            # Effects
            if effects:
                eff_str = ", ".join(f"+{v} {k}" for k, v in effects.items())
                print(f"      Effects: {eff_str}")

            if neg_effects:
                neg_str = ", ".join(f"-{v} {k}" for k, v in neg_effects.items())
                print(f"      Reduces: {neg_str}")

            # Employment
            if workers > 0:
                edu_parts = [
                    f"{k.replace('edu_', '')}: {int(v * 100)}%"
                    for k, v in sorted(edu.items())
                ]
                edu_str = ", ".join(edu_parts)
                print(f"      Employment: {workers:,} workers " f"[{edu_str}]")

    # SECTION 4: Debuffs & Penalties
    print("\n\n" + "=" * 80)
    print("4. DEBUFFS & CRISIS PENALTIES")
    print("=" * 80)

    print("\n  UNEMPLOYMENT DEBUFF:")
    print(
        f"    Trigger: {variables.UNEMPLOYMENT_THRESHOLD * 100:.0f}% "
        f"unemployment or higher"
    )
    print(
        f"    Penalty: -{variables.UNEMPLOYMENT_HAPPINESS_PENALTY} "
        f"happiness per province per tick"
    )

    print("\n  PENSION CRISIS DEBUFF:")
    print(
        f"    Trigger: Elderly > "
        f"{variables.PENSION_CRISIS_RATIO * 100:.0f}% of working pop"
    )
    print(
        f"    Penalty: -${variables.PENSION_CRISIS_GOLD_PENALTY:,} "
        f"gold per user per tick"
    )

    print("\n  PRODUCTION EFFICIENCY (Chernobyl Rule):")
    print("    Formula: jobs_available ÷ jobs_needed")
    print(
        f"    Floor: {variables.PRODUCTION_EFFICIENCY_MIN * 100:.0f}% "
        f"(minimum if understaffed)"
    )
    print("    Effect: ALL building production scaled by efficiency")
    print("    Example: 50% efficiency = farms produce 6 rations " "instead of 12")

    # SECTION 5: System Status
    print("\n\n" + "=" * 80)
    print("5. SYSTEM STATUS & FEATURE FLAGS")
    print("=" * 80)

    print(
        f"\n  Demographic Consumption: "
        f"{'ENABLED' if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION else 'DISABLED'}"
    )
    print(
        f"  Rations Distribution: "
        f"{'ENABLED' if variables.FEATURE_RATIONS_DISTRIBUTION else 'DISABLED'}"
    )
    print(
        f"  Phase 3 Workforce: "
        f"{'ENABLED' if variables.FEATURE_PHASE3_WORKFORCE else 'DISABLED'}"
    )

    print("\n" + "=" * 80)
    print("END OF MASTER AUDIT")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    generate_master_audit()
