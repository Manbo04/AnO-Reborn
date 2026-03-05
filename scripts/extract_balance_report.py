#!/usr/bin/env python3
"""Extract balance report from economy and workforce constants."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import variables  # noqa: E402


def generate_report():
    """Generate and print the balance report."""
    print("\n" + "=" * 80)
    print("AFFAIRS & ORDER: ECONOMY & DEMOGRAPHICS BALANCE REPORT")
    print("=" * 80)
    print("Generated: 4 March 2026\n")

    # SECTION 1: Demographic Rates
    print("\n1. DEMOGRAPHIC RATES (Per Tick)")
    print("-" * 80)
    aging_rates = variables.DEMO_AGING_RATES
    elderly_death = aging_rates.get("elderly_death_rate", 0) * 100
    working_to_elderly = aging_rates.get("working_to_elderly_rate", 0) * 100
    children_to_working = aging_rates.get("children_to_working_rate", 0) * 100
    print(f"  Elderly Death Rate:            {elderly_death:.1f}% per tick")
    print(f"  Working → Elderly Shift:       " f"{working_to_elderly:.1f}% per tick")
    print(f"  Children → Working Graduation: " f"{children_to_working:.1f}% per tick")

    # SECTION 2: Consumption Multipliers
    print("\n\n2. CONSUMPTION MULTIPLIERS (Per Capita Per Tick)")
    print("-" * 80)
    print("\n  RATIONS CONSUMPTION:")
    rations = variables.DEMO_RATIONS_CONSUMPTION
    rations_working = rations.get("pop_working", 0)
    rations_children = rations.get("pop_children", 0)
    rations_elderly = rations.get("pop_elderly", 0)
    print(f"    Working Population:  {rations_working} rations/person")
    print(f"    Children:            {rations_children} rations/person " "(+30%)")
    print(f"    Elderly:             {rations_elderly} rations/person " "(-20%)")

    print("\n  CONSUMER GOODS CONSUMPTION:")
    cg = variables.DEMO_CONSUMER_GOODS_CONSUMPTION
    cg_working = cg.get("pop_working", 0)
    cg_children = cg.get("pop_children", 0)
    cg_elderly = cg.get("pop_elderly", 0)
    print(f"    Working Population:  {cg_working} CG per person")
    print(f"    Children:            {cg_children} CG per person (+20%)")
    print(f"    Elderly:             {cg_elderly} CG per person (2x)")

    # SECTION 3: Production & Distribution
    print("\n\n3. PRODUCTION & DISTRIBUTION (Per Building Per Tick)")
    print("-" * 80)
    print("\n  PRIMARY PRODUCTION:")
    print("    Farms:               12 rations per building")

    print("\n  CONSUMER GOODS PRODUCTION (Retail):")
    print("    Malls:               30 consumer goods per building")
    print("    Farmers Markets:     16 consumer goods per building")
    print("    Gas Stations:        12 consumer goods per building")
    print("    General Stores:      10 consumer goods per building")
    print("    Banks:               20 consumer goods per building")

    print("\n  DISTRIBUTION CAPACITY LIMITS:")
    dist_cap = variables.CONSUMER_GOODS_DISTRIBUTION_PER_BUILDING
    cap_str = f"{dist_cap:,}"
    print(f"    All Distribution Buildings: {cap_str} population per")

    # SECTION 4: Employment Matrices
    print("\n\n4. EMPLOYMENT MATRICES (Jobs & Education Requirements)")
    print("-" * 80)

    matrices = variables.BUILDING_EMPLOYMENT_MATRICES

    categories = {
        "FOOD/BASIC": ["farms"],
        "POWER GENERATION": [
            "coal_burners",
            "oil_burners",
            "hydro_dams",
            "nuclear_reactors",
            "solar_fields",
        ],
        "MANUFACTURING": [
            "industrial_district",
            "component_factories",
            "steel_mills",
        ],
        "EDUCATION": ["primary_school", "high_school", "university"],
    }

    for category, buildings in categories.items():
        print(f"\n  {category}:")
        for bname in buildings:
            if bname in matrices:
                data = matrices[bname]
                workers = data.get("worker_count", 0)
                edu = data.get("education", {})
                edu_parts = [f"{k}: {int(v * 100)}%" for k, v in sorted(edu.items())]
                edu_str = ", ".join(edu_parts)
                print(f"    {bname:30} {workers:,} workers  " f"[{edu_str}]")
            else:
                print(f"    {bname:30} [NOT YET CONFIGURED]")

    # SECTION 5: Debuffs & Penalties
    print("\n\n5. DEBUFFS & PENALTIES (Chernobyl & Crisis System)")
    print("-" * 80)

    print("\n  UNEMPLOYMENT DEBUFF:")
    un_pct = variables.UNEMPLOYMENT_THRESHOLD * 100
    un_penalty = variables.UNEMPLOYMENT_HAPPINESS_PENALTY
    print(f"    Trigger Threshold:   {un_pct:.0f}% unemployment")
    print(f"    Happiness Penalty:   -{un_penalty} per province/tick")

    print("\n  PENSION CRISIS DEBUFF:")
    pension_pct = variables.PENSION_CRISIS_RATIO * 100
    pension_penalty = variables.PENSION_CRISIS_GOLD_PENALTY
    print(f"    Trigger Threshold:   Elderly > {pension_pct:.0f}% of workers")
    print(f"    Gold Penalty:        -{pension_penalty:,} per user/tick")

    print("\n  PRODUCTION EFFICIENCY (Chernobyl Rule):")
    eff_min = variables.PRODUCTION_EFFICIENCY_MIN * 100
    print("    Calculation:         jobs_available / jobs_needed")
    print(f"    Efficiency Floor:    {eff_min:.0f}% (if understaffed)")
    print("    Effect:              ALL production multiplied by factor")

    # SECTION 6: Feature Flags
    print("\n\n6. SYSTEM STATUS (Feature Flags)")
    print("-" * 80)
    demo_status = "ENABLED" if variables.FEATURE_DEMOGRAPHIC_CONSUMPTION else "DISABLED"
    rations_status = "ENABLED" if variables.FEATURE_RATIONS_DISTRIBUTION else "DISABLED"
    phase3_status = "ENABLED" if variables.FEATURE_PHASE3_WORKFORCE else "DISABLED"
    print(f"  Demographic-Based Consumption:  {demo_status}")
    print(f"  Rations Distribution Bottleneck: {rations_status}")
    print(f"  Phase 3 Workforce/Employment:   {phase3_status}")

    print("\n" + "=" * 80)
    print("END OF REPORT")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    generate_report()
