#!/usr/bin/env python3
"""
Normalize population to sustainable limits.

After the population growth fix, some players have populations that exceed
the maximum sustainable cap based on their cities and land. This script
caps all provinces to their calculated maximum population.

Formula: max_pop = 1,000,000 + (cities * 750,000) + (land * 120,000)
         (with happiness/pollution modifiers applied)

Run with --dry-run first to see what changes would be made.
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import variables
from database import get_db_connection


def calculate_max_population(cities, land, happiness=50, pollution=50):
    """Calculate the maximum population for a province."""
    max_pop = variables.DEFAULT_MAX_POPULATION  # 1,000,000
    max_pop += cities * variables.CITY_MAX_POPULATION_ADDITION  # 750,000 per city
    max_pop += land * variables.LAND_MAX_POPULATION_ADDITION  # 120,000 per land

    # Apply happiness/pollution modifiers (same as in population_growth)
    happiness_multiplier = (
        (happiness - 50) * variables.DEFAULT_HAPPINESS_GROWTH_MULTIPLIER / 50
    )
    pollution_multiplier = (
        (pollution - 50) * -variables.DEFAULT_POLLUTION_GROWTH_MULTIPLIER / 50
    )

    max_pop = int(max_pop * (1 + happiness_multiplier + pollution_multiplier))

    if max_pop < variables.DEFAULT_MAX_POPULATION:
        max_pop = variables.DEFAULT_MAX_POPULATION

    return max_pop


def normalize_populations(dry_run=True):
    """Cap all provinces to their sustainable maximum population."""
    with get_db_connection() as conn:
        db = conn.cursor()

        # Get all provinces with their current stats
        db.execute(
            """
            SELECT
                p.id,
                p.userId,
                u.username,
                p.population,
                COALESCE(p.cityCount, 0) as cities,
                COALESCE(p.land, 0) as land,
                COALESCE(p.happiness, 50) as happiness,
                COALESCE(p.pollution, 50) as pollution
            FROM provinces p
            LEFT JOIN users u ON u.id = p.userId
            ORDER BY p.population DESC
        """
        )
        provinces = db.fetchall()

        updates = []
        total_reduced = 0

        print("\n" + "=" * 80)
        print("POPULATION NORMALIZATION REPORT")
        print("=" * 80 + "\n")

        for row in provinces:
            prov_id, user_id, username, pop, cities, land, happiness, pollution = row

            max_pop = calculate_max_population(cities, land, happiness, pollution)

            if pop > max_pop:
                reduction = pop - max_pop
                total_reduced += reduction
                updates.append((max_pop, prov_id))

                print(f"Province {prov_id} ({username or 'Unknown'}):")
                print(f"  Cities: {cities}, Land: {land}")
                print(f"  Current: {pop:,} → Max allowed: {max_pop:,}")
                print(f"  Reduction: -{reduction:,} ({reduction * 100 // pop}%)")
                print()

        print("-" * 80)
        print(f"SUMMARY:")
        print(f"  Provinces affected: {len(updates)}")
        print(f"  Total population to reduce: {total_reduced:,}")
        print("-" * 80)

        if dry_run:
            print(
                "\n⚠️  DRY RUN - No changes made. Run with --apply to make changes.\n"
            )
        else:
            if updates:
                from psycopg2.extras import execute_batch

                execute_batch(
                    db,
                    "UPDATE provinces SET population = %s WHERE id = %s",
                    updates,
                )
                conn.commit()
                print(f"\n✅ Applied {len(updates)} population caps.\n")
            else:
                print("\n✅ No provinces exceeded their limits. Nothing to do.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Normalize province populations to sustainable limits"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually apply the changes (default is dry-run)",
    )
    args = parser.parse_args()

    normalize_populations(dry_run=not args.apply)


if __name__ == "__main__":
    main()
