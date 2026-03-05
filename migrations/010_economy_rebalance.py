#!/usr/bin/env python3
"""Migration 010: Early-game economy rebalance.

Adds missing buildings to building_dictionary, inserts distribution_centers,
fixes aerodromes name mismatch, updates starter gold to 80M, and backfills
user_buildings rows for all existing users.

Run: python migrations/010_economy_rebalance.py
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection  # noqa: E402


def run():
    with get_db_connection() as conn:
        db = conn.cursor()

        # ── 1. Fix aerodomes → aerodromes mismatch ──────────────────────
        # The DB already has 'aerodromes' (building_id=15), but all Python
        # code and templates use 'aerodomes'.  Rename the DB entry to match
        # the codebase convention (shorter, used everywhere).
        print("[1/6] Fixing aerodromes → aerodomes name mismatch...")
        db.execute(
            "UPDATE building_dictionary SET name = 'aerodomes' "
            "WHERE name = 'aerodromes' AND building_id = 15"
        )
        print(f"  Updated {db.rowcount} row(s)")

        # ── 2. Insert missing buildings ──────────────────────────────────
        # These exist in variables.py but were never added to building_dictionary.
        # Without them, they don't appear in the Quick Build menu and
        # new users don't get user_buildings rows for them.
        print("[2/6] Inserting missing buildings into building_dictionary...")

        missing_buildings = [
            # (name, display_name, category, base_cost,
            #  effect_type, effect_value, maintenance_cost, description)
            # Valid effect_types: resource_production,
            #   population_growth, happiness, military_boost,
            #   research_speed, tax_income,
            #   energy_production, unit_capacity
            (
                "solar_fields",
                "Solar Fields",
                "energy",
                8000000,
                "energy_production",
                "3",
                13000,
                "Clean energy from sunlight. No fuel required.",
            ),
            (
                "hydro_dams",
                "Hydro Dams",
                "energy",
                35000000,
                "energy_production",
                "6",
                24000,
                "Large-scale hydroelectric power generation.",
            ),
            (
                "gas_stations",
                "Gas Stations",
                "commerce",
                7000000,
                "resource_production",
                "12",
                20000,
                "Retail fuel stations that also distribute consumer goods.",
            ),
            (
                "farmers_markets",
                "Farmers Markets",
                "commerce",
                4500000,
                "resource_production",
                "16",
                80000,
                "Local food distribution and rations availability.",
            ),
            (
                "city_parks",
                "City Parks",
                "civic",
                4500000,
                "happiness",
                "5",
                25000,
                "Green spaces that increase happiness and reduce pollution.",
            ),
            (
                "monorails",
                "Monorails",
                "civic",
                250000000,
                "resource_production",
                "16",
                270000,
                "High-speed urban transit boosting productivity.",
            ),
            (
                "admin_buildings",
                "Administrative Buildings",
                "military",
                50000000,
                "military_boost",
                "1",
                90000,
                "Enable spy recruitment and intelligence operations.",
            ),
            (
                "silos",
                "Silos",
                "military",
                350000000,
                "unit_capacity",
                "1",
                340000,
                "Store and launch ballistic missiles and nuclear weapons.",
            ),
            (
                "lumber_mills",
                "Lumber Mills",
                "resource_production",
                2200000,
                "resource_production",
                "35",
                7500,
                "Harvest and process timber into lumber.",
            ),
            (
                "iron_mines",
                "Iron Mines",
                "resource_production",
                3800000,
                "resource_production",
                "23",
                11000,
                "Extract iron ore from underground deposits.",
            ),
            (
                "bauxite_mines",
                "Bauxite Mines",
                "resource_production",
                3200000,
                "resource_production",
                "20",
                8000,
                "Mine raw bauxite for aluminium production.",
            ),
            (
                "copper_mines",
                "Copper Mines",
                "resource_production",
                2800000,
                "resource_production",
                "25",
                5000,
                "Extract copper ore used in components and ammunition.",
            ),
            (
                "uranium_mines",
                "Uranium Mines",
                "resource_production",
                5500000,
                "resource_production",
                "12",
                45000,
                "Mine radioactive uranium for nuclear power.",
            ),
            (
                "lead_mines",
                "Lead Mines",
                "resource_production",
                2600000,
                "resource_production",
                "19",
                7200,
                "Mine lead used in ammunition production.",
            ),
            (
                "distribution_centers",
                "Distribution Centers",
                "commerce",
                5000000,
                "resource_production",
                "400000",
                15000,
                "Large-scale logistics hubs that distribute rations"
                " and consumer goods to 400,000 citizens each.",
            ),
        ]

        inserted = 0
        for (
            name,
            display_name,
            category,
            base_cost,
            effect_type,
            effect_value,
            maintenance_cost,
            description,
        ) in missing_buildings:
            db.execute(
                """
                INSERT INTO building_dictionary
                    (name, display_name, category, base_cost, effect_type,
                     effect_value, maintenance_cost, description, is_active)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (name) DO NOTHING
                """,
                (
                    name,
                    display_name,
                    category,
                    str(base_cost),
                    effect_type,
                    str(effect_value),
                    str(maintenance_cost),
                    description,
                ),
            )
            if db.rowcount > 0:
                inserted += 1
                print(f"  + {name}")
            else:
                print(f"  ~ {name} (already exists)")

        print(f"  Inserted {inserted} new buildings")

        # ── 3. Backfill user_buildings for ALL existing users ────────────
        # Any user missing rows for newly-added buildings gets them at qty 0.
        print("[3/6] Backfilling user_buildings for new building types...")
        db.execute(
            """
            INSERT INTO user_buildings (user_id, building_id, quantity)
            SELECT u.id, bd.building_id, 0
            FROM users u
            CROSS JOIN building_dictionary bd
            WHERE bd.is_active = TRUE
            ON CONFLICT (user_id, building_id) DO NOTHING
            """
        )
        print(f"  Backfilled {db.rowcount} rows")

        # ── 4. Update starter gold: 20M → 80M ───────────────────────────
        print("[4/6] Updating starter gold default to 80,000,000...")
        db.execute("ALTER TABLE stats ALTER COLUMN gold SET DEFAULT 80000000")
        print("  Done")

        # ── 5. Commit everything ─────────────────────────────────────────
        print("[5/6] Committing transaction...")
        conn.commit()
        print("Migration 010 complete!")

        # Verify
        db.execute("SELECT count(*) FROM building_dictionary WHERE is_active = TRUE")
        total = db.fetchone()[0]
        print(f"\nTotal active buildings in dictionary: {total}")

        db.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='stats' AND column_name='gold'"
        )
        default = db.fetchone()[0]
        print(f"Stats.gold default: {default}")


if __name__ == "__main__":
    run()
