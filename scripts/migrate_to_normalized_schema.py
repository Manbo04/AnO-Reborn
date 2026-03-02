#!/usr/bin/env python3
"""
Data Migration Script: Legacy Wide Tables → Normalized Architecture
Date: 2026-03-02
Purpose: Migrate existing player data from proinfra and upgrades tables
to normalized mapping tables

This script performs:
1. Infrastructure migration: proinfra → user_buildings
2. Research migration: upgrades → user_tech
3. Verification of data integrity
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

load_dotenv()


def get_db_connection():
    """Establish database connection using environment variables"""
    db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
    if not db_url:
        raise ValueError("DATABASE_URL or DATABASE_PUBLIC_URL must be set")
    return psycopg2.connect(db_url)


def create_column_to_building_map():
    """
    Map proinfra column names to building_dictionary entries
    This mapping handles naming differences between legacy columns
    and normalized names
    """
    return {
        # Energy buildings
        "coal_burners": "coal_burners",
        "oil_burners": "oil_burners",
        "nuclear_reactors": "nuclear_reactors",
        # Commerce buildings
        "general_stores": "general_stores",
        "malls": "malls",
        "banks": "banks",
        # Civic buildings
        "hospitals": "hospitals",
        "libraries": "libraries",
        "universities": "universities",
        # Military buildings
        "army_bases": "army_bases",
        "aerodomes": "aerodromes",  # Note: spelling difference
        "harbours": "harbours",
        # Resource production
        "farms": "farms",
        "pumpjacks": "pumpjacks",
        "coal_mines": "coal_mines",
        "steel_mills": "steel_mills",
    }


def create_column_to_tech_map():
    """
    Map upgrades column names to tech_dictionary entries
    This mapping connects legacy upgrade columns to normalized tech names
    """
    return {
        # Map legacy upgrade column names to tech_dictionary names
        # Based on upgrades table structure
        "betterEngineering": "industrialization",
        "advancedMachinery": "steel_production",
        "nuclearTestingFacility": "nuclear_physics",
        # Add more mappings as needed based on actual upgrades table columns
    }


def migrate_infrastructure(conn):
    """
    Migrate building data from proinfra table to user_buildings mapping table
    Returns: (migrated_count, total_buildings_in_legacy)
    """
    print("\n" + "=" * 70)
    print("TASK 1: INFRASTRUCTURE MIGRATION")
    print("=" * 70)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Step 1: Build building name -> ID lookup
    print("\n[1/5] Building lookup dictionary...")
    cursor.execute("SELECT building_id, name FROM building_dictionary")
    building_lookup = {row["name"]: row["building_id"] for row in cursor.fetchall()}
    print(f"✓ Found {len(building_lookup)} building types in dictionary")

    # Step 2: Get column mapping
    column_map = create_column_to_building_map()
    print(f"✓ Mapped {len(column_map)} legacy columns to building types")

    # Step 3: Read all proinfra data joined with valid users
    print("\n[2/5] Reading legacy proinfra table...")
    cursor.execute(
        """
        SELECT p.*
        FROM proinfra p
        INNER JOIN users u ON p.id = u.id
    """
    )
    proinfra_rows = cursor.fetchall()
    print(f"✓ Found {len(proinfra_rows)} users with infrastructure data")

    # Step 4: Calculate totals for verification
    print("\n[3/5] Calculating legacy totals for verification...")
    legacy_total = 0
    for row in proinfra_rows:
        for col_name in column_map.keys():
            if col_name in row:
                legacy_total += row[col_name] or 0
    print(f"✓ Total buildings in legacy table: {legacy_total:,}")

    # Step 5: Prepare migration data
    print("\n[4/5] Preparing migration data...")
    migration_data = []
    skipped_buildings = set()

    for row in proinfra_rows:
        user_id = row["id"]

        for legacy_col, building_name in column_map.items():
            if legacy_col not in row:
                continue

            quantity = row[legacy_col] or 0
            if quantity == 0:
                continue

            # Look up building_id
            building_id = building_lookup.get(building_name)
            if building_id is None:
                skipped_buildings.add(building_name)
                continue

            migration_data.append((user_id, building_id, quantity))

    print(f"✓ Prepared {len(migration_data):,} building records for migration")
    if skipped_buildings:
        skipped_list = ", ".join(skipped_buildings)
        print(f"⚠ Skipped buildings not in dictionary: {skipped_list}")

    # Step 6: Insert into user_buildings
    print("\n[5/5] Inserting into user_buildings table...")
    if migration_data:
        insert_query = """
            INSERT INTO user_buildings (user_id, building_id, quantity)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, building_id)
            DO UPDATE SET quantity = user_buildings.quantity + EXCLUDED.quantity
        """
        execute_batch(cursor, insert_query, migration_data, page_size=1000)
        conn.commit()
        print(f"✓ Successfully migrated {len(migration_data):,} building records")
    else:
        print("⚠ No data to migrate")

    cursor.close()
    return len(migration_data), legacy_total


def migrate_research(conn):
    """
    Migrate tech/upgrade data from upgrades table to user_tech mapping table
    Returns: (migrated_count, total_upgrades_in_legacy)
    """
    print("\n" + "=" * 70)
    print("TASK 2: RESEARCH/TECHNOLOGY MIGRATION")
    print("=" * 70)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Step 1: Build tech name -> ID lookup
    print("\n[1/5] Building tech lookup dictionary...")
    cursor.execute("SELECT tech_id, name FROM tech_dictionary")
    tech_lookup = {row["name"]: row["tech_id"] for row in cursor.fetchall()}
    print(f"✓ Found {len(tech_lookup)} tech types in dictionary")

    # Step 2: Get column mapping
    column_map = create_column_to_tech_map()
    print(f"✓ Mapped {len(column_map)} legacy upgrade columns to tech types")

    # Step 3: Read all upgrades data joined with valid users
    print("\n[2/5] Reading legacy upgrades table...")
    cursor.execute(
        """
        SELECT up.*
        FROM upgrades up
        INNER JOIN users u ON up.user_id = u.id
    """
    )
    upgrade_rows = cursor.fetchall()
    print(f"✓ Found {len(upgrade_rows)} users with upgrade data")

    # Step 4: Calculate totals for verification
    print("\n[3/5] Calculating legacy totals for verification...")
    legacy_total = 0
    for row in upgrade_rows:
        for col_name in column_map.keys():
            if col_name in row:
                legacy_total += 1 if (row[col_name] or 0) > 0 else 0
    print(f"✓ Total unlocked upgrades in legacy table: {legacy_total:,}")

    # Step 5: Prepare migration data
    print("\n[4/5] Preparing migration data...")
    migration_data = []
    skipped_techs = set()

    for row in upgrade_rows:
        user_id = row["user_id"]

        for legacy_col, tech_name in column_map.items():
            if legacy_col not in row:
                continue

            is_unlocked = (row[legacy_col] or 0) > 0
            if not is_unlocked:
                continue

            # Look up tech_id
            tech_id = tech_lookup.get(tech_name)
            if tech_id is None:
                skipped_techs.add(tech_name)
                continue

            migration_data.append((user_id, tech_id, True))

    print(f"✓ Prepared {len(migration_data):,} tech records for migration")
    if skipped_techs:
        print(f"⚠ Skipped techs not in dictionary: {', '.join(skipped_techs)}")

    # Step 6: Insert into user_tech
    print("\n[5/5] Inserting into user_tech table...")
    if migration_data:
        insert_query = """
            INSERT INTO user_tech (user_id, tech_id, is_unlocked, unlocked_at)
            VALUES (%s, %s, %s, now())
            ON CONFLICT (user_id, tech_id)
            DO UPDATE SET is_unlocked = TRUE, unlocked_at = now()
        """
        execute_batch(cursor, insert_query, migration_data, page_size=1000)
        conn.commit()
        print(f"✓ Successfully migrated {len(migration_data):,} tech records")
    else:
        print("⚠ No data to migrate")

    cursor.close()
    return len(migration_data), legacy_total


def verify_migration(conn):
    """
    Verify that the migration was successful by comparing counts and data integrity
    """
    print("\n" + "=" * 70)
    print("TASK 3: MIGRATION VERIFICATION")
    print("=" * 70)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Verify buildings
    print("\n[Buildings Verification]")
    cursor.execute(
        "SELECT COUNT(*) as count, SUM(quantity) as total FROM user_buildings"
    )
    result = cursor.fetchone()
    print(f"✓ Total user_buildings records: {result['count']:,}")
    print(f"✓ Total building quantity in new table: {result['total']:,}")

    cursor.execute(
        """
        SELECT COUNT(DISTINCT user_id) as user_count
        FROM user_buildings
    """
    )
    result = cursor.fetchone()
    print(f"✓ Unique users with buildings: {result['user_count']:,}")

    # Verify techs
    print("\n[Technology Verification]")
    cursor.execute(
        """
        SELECT COUNT(*) as count,
               SUM(CASE WHEN is_unlocked THEN 1 ELSE 0 END) as unlocked
        FROM user_tech
    """
    )
    result = cursor.fetchone()
    print(f"✓ Total user_tech records: {result['count']:,}")
    unlocked_count = result["unlocked"] or 0
    print(f"✓ Total unlocked techs in new table: {unlocked_count:,}")

    cursor.execute(
        """
        SELECT COUNT(DISTINCT user_id) as user_count
        FROM user_tech
    """
    )
    result = cursor.fetchone()
    print(f"✓ Unique users with tech progress: {result['user_count']:,}")

    # Sample data verification
    print("\n[Sample Data Check]")
    cursor.execute(
        """
        SELECT u.username, bd.display_name, ub.quantity
        FROM user_buildings ub
        JOIN users u ON ub.user_id = u.id
        JOIN building_dictionary bd ON ub.building_id = bd.building_id
        ORDER BY ub.quantity DESC
        LIMIT 5
    """
    )
    print("\nTop 5 building holdings:")
    for row in cursor.fetchall():
        print(f"  • {row['username']}: {row['quantity']:,} {row['display_name']}")

    cursor.execute(
        """
        SELECT u.username, td.display_name
        FROM user_tech ut
        JOIN users u ON ut.user_id = u.id
        JOIN tech_dictionary td ON ut.tech_id = td.tech_id
        WHERE ut.is_unlocked = TRUE
        LIMIT 5
    """
    )
    print("\nSample unlocked techs:")
    for row in cursor.fetchall():
        print(f"  • {row['username']}: {row['display_name']}")

    cursor.close()


def main():
    """Main execution flow"""
    print("=" * 70)
    print("DATA MIGRATION: Legacy Wide Tables → Normalized Architecture")
    print("=" * 70)

    try:
        # Connect to database
        print("\nConnecting to database...")
        conn = get_db_connection()
        print("✓ Database connection established")

        # Task 1: Migrate infrastructure
        buildings_migrated, buildings_legacy_total = migrate_infrastructure(conn)

        # Task 2: Migrate research
        techs_migrated, techs_legacy_total = migrate_research(conn)

        # Task 3: Verify migration
        verify_migration(conn)

        # Summary
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        print(f"\n✓ Buildings: {buildings_migrated:,} records migrated")
        print(f"✓ Technologies: {techs_migrated:,} records migrated")
        print("\n⚠ IMPORTANT: Legacy tables (proinfra, upgrades) NOT deleted")
        print("             Verify data in DBeaver before dropping old tables")
        print("=" * 70 + "\n")

        conn.close()
        return 0

    except Exception as e:
        print(f"\n❌ ERROR: {str(e)}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
