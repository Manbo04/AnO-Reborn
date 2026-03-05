#!/usr/bin/env python3
"""
Census Migration Script: Distribute Population into Demographics
and Education Levels
Date: 2026-03-04
Purpose: Safely convert single population integer into age brackets
and education levels

Steps:
1. Run SQL migration to add new columns to provinces table
2. Distribute existing population: 20% children, 65% working, 15% elderly
3. Assign 100% of working population to edu_none education level
4. Add new buildings to building_dictionary (Industrial District,
   Primary School, High School, University)
5. Verify integrity: sum of brackets = original population
"""

import os
import sys
import logging
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_batch
from contextlib import contextmanager

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    """Get database connection from environment"""
    conn = psycopg2.connect(
        host=os.getenv("PG_HOST", "localhost"),
        port=os.getenv("PG_PORT", "5432"),
        user=os.getenv("PG_USER", "postgres"),
        password=os.getenv("PG_PASSWORD", ""),
        database=os.getenv("PG_DATABASE", "postgres"),
    )
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database transaction failed: {e}")
        raise
    finally:
        conn.close()


def run_sql_migration():
    """Execute the SQL migration to add new columns to provinces"""
    logger.info("=" * 70)
    logger.info("STEP 1: Running SQL migration to add demographic columns...")
    logger.info("=" * 70)

    migration_file = (
        "/Users/dede/AnO/migrations/0013_add_demographics_education_schema.sql"
    )

    if not os.path.exists(migration_file):
        logger.error(f"Migration file not found: {migration_file}")
        sys.exit(1)

    with open(migration_file, "r") as f:
        sql_migration = f.read()

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(sql_migration)
                logger.info("✓ SQL migration executed successfully")
            except Exception as e:
                logger.error(f"SQL migration failed: {e}")
                raise


def distribute_population():
    """
    Distribute existing population into age brackets.

    Distribution:
    - pop_children: 20% of population
    - pop_working: 65% of population
    - pop_elderly: 15% of population

    All working population initialized to edu_none: 100% of pop_working
    """
    logger.info("=" * 70)
    logger.info("STEP 2: Distributing existing population into age brackets...")
    logger.info("=" * 70)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Fetch all provinces with their current population
            cur.execute(
                """
                SELECT id, userId, population
                FROM provinces
                WHERE population > 0
                ORDER BY id
            """
            )
            provinces = cur.fetchall()
            logger.info(f"Found {len(provinces)} provinces with population > 0")

            # Prepare batch update data
            update_data = []
            total_provinces_processed = 0
            total_people_before = 0
            total_people_after = 0

            for province_id, user_id, population in provinces:
                # Calculate brackets with rounding to ensure no loss
                pop_children = int(population * 0.20)
                pop_elderly = int(population * 0.15)
                pop_working = (
                    population - pop_children - pop_elderly
                )  # Remainder ensures total = original

                # All working population starts as edu_none
                edu_none_count = pop_working

                update_data.append(
                    (
                        pop_children,
                        pop_working,
                        pop_elderly,
                        edu_none_count,  # edu_none
                        0,  # edu_highschool
                        0,  # edu_college
                        province_id,
                    )
                )

                total_people_before += population
                total_people_after += pop_children + pop_working + pop_elderly
                total_provinces_processed += 1

                # Log sample if it's the first few or every 100th
                if (
                    total_provinces_processed <= 3
                    or total_provinces_processed % 100 == 0
                ):
                    msg = (
                        f"  Province {province_id} (User {user_id}): "
                        f"pop {population} → "
                        f"children={pop_children}, "
                        f"working={pop_working}, elderly={pop_elderly}"
                    )
                    logger.info(msg)

            # Execute batch update
            update_sql = """
                UPDATE provinces
                SET pop_children = %s,
                    pop_working = %s,
                    pop_elderly = %s,
                    edu_none = %s,
                    edu_highschool = %s,
                    edu_college = %s
                WHERE id = %s
            """

            execute_batch(cur, update_sql, update_data, page_size=1000)
            logger.info(f"✓ Updated {total_provinces_processed} provinces")

            # Verify integrity
            logger.info("Verifying population integrity...")
            cur.execute(
                """
                SELECT
                    COUNT(*) as province_count,
                    SUM(population) as total_pop_old,
                    SUM(pop_children + pop_working + pop_elderly)
                        as total_pop_new,
                    COUNT(CASE
                        WHEN (pop_children + pop_working + pop_elderly)
                            != population
                        THEN 1
                    END) as mismatches
                FROM provinces
            """
            )

            result = cur.fetchone()
            province_count, total_old, total_new, mismatches = result

            logger.info("\nPopulation Distribution Summary:")
            logger.info(f"  Provinces processed: {province_count}")
            logger.info(f"  Total population (old): {total_old or 0}")
            logger.info(f"  Total population (new brackets): {total_new or 0}")
            logger.info(f"  Provinces with mismatched totals: {mismatches or 0}")

            if mismatches and mismatches > 0:
                msg = (
                    f"⚠ Found {mismatches} provinces with "
                    f"mismatched population totals!"
                )
                logger.warning(msg)
                logger.warning("  This indicates rounding errors - inspecting...")
                cur.execute(
                    """
                    SELECT id, population,
                        (pop_children + pop_working + pop_elderly)
                        as new_total
                    FROM provinces
                    WHERE (pop_children + pop_working + pop_elderly)
                        != population
                    LIMIT 10
                """
                )
                for row in cur.fetchall():
                    logger.warning(f"    Province {row[0]}: old={row[1]}, new={row[2]}")
            else:
                logger.info("✓ Population integrity verified - no mismatches!")


def add_new_buildings():
    """Add new buildings to building_dictionary"""
    logger.info("=" * 70)
    logger.info("STEP 3: Adding new buildings to building_dictionary...")
    logger.info("=" * 70)

    new_buildings = [
        {
            "name": "industrial_district",
            "display_name": "Industrial District",
            "category": "resource_production",
            "base_cost": 40000,
            "effect_type": "resource_production",
            "effect_value": 150.0,
            "maintenance_cost": 400,
            "description": (
                "Advanced manufacturing hub producing " "consumer goods and components"
            ),
        },
        {
            "name": "primary_school",
            "display_name": "Primary School",
            "category": "civic",
            "base_cost": 12000,
            "effect_type": "population_growth",
            "effect_value": 3.0,
            "maintenance_cost": 150,
            "description": (
                "Elementary education facility establishing " "baseline education"
            ),
        },
        {
            "name": "high_school",
            "display_name": "High School",
            "category": "civic",
            "base_cost": 20000,
            "effect_type": "research_speed",
            "effect_value": 7.0,
            "maintenance_cost": 250,
            "description": (
                "Secondary education institution advancing " "student knowledge"
            ),
        },
        {
            "name": "university",
            "display_name": "University",
            "category": "civic",
            "base_cost": 35000,
            "effect_type": "research_speed",
            "effect_value": 15.0,
            "maintenance_cost": 400,
            "description": (
                "Higher education institution driving advanced "
                "research and innovation"
            ),
        },
    ]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            insert_sql = """
                INSERT INTO building_dictionary (
                    name, display_name, category, base_cost, effect_type,
                    effect_value, maintenance_cost, description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            """

            inserted_count = 0
            for building in new_buildings:
                try:
                    cur.execute(
                        insert_sql,
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

                    if cur.rowcount > 0:
                        logger.info(f"  ✓ Added building: {building['display_name']}")
                        inserted_count += 1
                    else:
                        logger.info(
                            f"  - Skipped (already exists): {building['display_name']}"
                        )
                except Exception as e:
                    logger.error(
                        f"  ✗ Failed to insert {building['display_name']}: {e}"
                    )
                    raise

            logger.info(f"✓ {inserted_count} new buildings added")


def verify_columns_exist():
    """Verify that all new columns exist in the provinces table"""
    logger.info("=" * 70)
    logger.info("STEP 4: Verifying column creation...")
    logger.info("=" * 70)

    required_columns = [
        "pop_children",
        "pop_working",
        "pop_elderly",
        "edu_none",
        "edu_highschool",
        "edu_college",
    ]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'provinces'
            """
            )

            existing_columns = {row[0] for row in cur.fetchall()}

            all_exist = True
            for column in required_columns:
                if column in existing_columns:
                    logger.info(f"  ✓ Column '{column}' exists")
                else:
                    logger.error(f"  ✗ Column '{column}' NOT FOUND")
                    all_exist = False

            if all_exist:
                logger.info("✓ All demographic and education columns verified!")
            else:
                logger.error("✗ Some required columns are missing!")
                sys.exit(1)


def verify_buildings_exist():
    """Verify that new buildings were inserted"""
    logger.info("=" * 70)
    logger.info("STEP 5: Verifying building insertion...")
    logger.info("=" * 70)

    building_names = [
        "industrial_district",
        "primary_school",
        "high_school",
        "university",
    ]

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for building_name in building_names:
                cur.execute(
                    "SELECT building_id, display_name "
                    "FROM building_dictionary WHERE name = %s",
                    (building_name,),
                )
                result = cur.fetchone()

                if result:
                    logger.info(f"  ✓ Building found: {result[1]} (ID: {result[0]})")
                else:
                    logger.warning(f"  ? Building not found: {building_name}")


def main():
    """Execute the full migration"""
    logger.info("\n")
    logger.info("╔" + "=" * 68 + "╗")
    logger.info(
        "║"
        + " CENSUS MIGRATION: Population Demographics & Education Schema ".center(68)
        + "║"
    )
    logger.info("╚" + "=" * 68 + "╝")
    logger.info("")

    try:
        run_sql_migration()
        distribute_population()
        add_new_buildings()
        verify_columns_exist()
        verify_buildings_exist()

        logger.info("\n")
        logger.info("╔" + "=" * 68 + "╗")
        logger.info("║" + " MIGRATION COMPLETED SUCCESSFULLY ".center(68) + "║")
        logger.info("╚" + "=" * 68 + "╝")
        logger.info("")

    except Exception as e:
        logger.error("\n")
        logger.error("╔" + "=" * 68 + "╗")
        logger.error("║" + " MIGRATION FAILED ".center(68) + "║")
        logger.error("╚" + "=" * 68 + "╝")
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
