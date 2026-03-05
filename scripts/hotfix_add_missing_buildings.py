#!/usr/bin/env python3
"""
CRITICAL HOTFIX: Add missing processing buildings to building_dictionary

Root Cause: Economy 2.0 migration created building_dictionary but forgot to add
processing buildings (oil_refineries, aluminium_refineries,
component_factories, ammunition_factories).

Without oil_refineries, players cannot produce gasoline. This caused all
gasoline reserves to deplete, triggering the unit desertion mechanic which
deleted all tanks, artillery, and other gasoline-consuming units.

This script adds the missing buildings and grants compensation gasoline to
affected players.
"""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection  # noqa: E402

# Add missing buildings to building_dictionary
MISSING_BUILDINGS = [
    {
        "name": "oil_refineries",
        "display_name": "Oil Refineries",
        "category": "resource_production",
        "base_cost": 35000,
        "effect_type": "resource_production",
        "effect_value": 0,
        "maintenance_cost": 35000,
        "description": "Refine oil into gasoline for military vehicles and aircraft",
    },
    {
        "name": "aluminium_refineries",
        "display_name": "Aluminium Refineries",
        "category": "resource_production",
        "base_cost": 42000,
        "effect_type": "resource_production",
        "effect_value": 0,
        "maintenance_cost": 42000,
        "description": "Refine bauxite into aluminium for aircraft production",
    },
    {
        "name": "component_factories",
        "display_name": "Component Factories",
        "category": "resource_production",
        "base_cost": 50000,
        "effect_type": "resource_production",
        "effect_value": 0,
        "maintenance_cost": 50000,
        "description": "Produce military components from copper, steel, and aluminium",
    },
    {
        "name": "ammunition_factories",
        "display_name": "Ammunition Factories",
        "category": "resource_production",
        "base_cost": 15000,
        "effect_type": "resource_production",
        "effect_value": 0,
        "maintenance_cost": 15000,
        "description": "Produce ammunition from copper and lead",
    },
]


def main():
    print("=" * 70)
    print("CRITICAL HOTFIX: Adding missing processing buildings")
    print("=" * 70)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Check which buildings are missing
            cur.execute("SELECT name FROM building_dictionary")
            existing = {row[0] for row in cur.fetchall()}

            buildings_to_add = [
                b for b in MISSING_BUILDINGS if b["name"] not in existing
            ]

            if not buildings_to_add:
                print("✓ All processing buildings already exist")
                return

            print(f"\nAdding {len(buildings_to_add)} missing buildings:")
            for building in buildings_to_add:
                print(f"  - {building['display_name']} ({building['name']})")

            # Insert missing buildings
            for building in buildings_to_add:
                cur.execute(
                    """
                    INSERT INTO building_dictionary
                        (name, display_name, category, base_cost, effect_type,
                         effect_value, maintenance_cost, description, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true)
                    """,
                    (
                        building["name"],
                        building["display_name"],
                        building["category"],
                        building["base_cost"],
                        building["effect_type"],
                        building["effect_value"],
                        building["maintenance_cost"],
                        building["description"],
                    ),
                )

            conn.commit()
            print("\n✓ Buildings added successfully")

            # Grant compensation gasoline to all players
            print(
                "\nGranting compensation gasoline (500,000 kg) to all active players..."
            )
            cur.execute(
                """
                SELECT resource_id FROM resource_dictionary WHERE name = 'gasoline'
            """
            )
            gasoline_id = cur.fetchone()[0]

            cur.execute(
                """
                INSERT INTO user_economy (user_id, resource_id, quantity)
                SELECT id, %s, 500000
                FROM users
                WHERE id > 0
                ON CONFLICT (user_id, resource_id)
                DO UPDATE SET quantity = user_economy.quantity + 500000
            """,
                (gasoline_id,),
            )

            affected = cur.rowcount
            conn.commit()
            print(f"✓ Granted gasoline to {affected} players")

    print("\n" + "=" * 70)
    print("HOTFIX COMPLETE")
    print("=" * 70)
    print("\nPlayers can now:")
    print("  1. Build Oil Refineries to produce gasoline")
    print("  2. Rebuild their tanks and artillery units")
    print("  3. Resume normal military operations")
    print()


if __name__ == "__main__":
    main()
