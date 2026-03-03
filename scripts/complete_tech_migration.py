#!/usr/bin/env python3
"""
Complete Tech Migration Script
Scans legacy upgrades table, creates missing tech_dictionary entries,
and migrates all tech data to user_tech table
"""

import os
import sys
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch

load_dotenv()


def get_db_connection():
    """Establish database connection"""
    db_url = os.getenv("DATABASE_URL") or os.getenv("DATABASE_PUBLIC_URL")
    if not db_url:
        raise ValueError("DATABASE_URL must be set")
    return psycopg2.connect(db_url)


# Complete mapping of legacy upgrade columns to normalized tech names
LEGACY_TECH_MAPPINGS = {
    "betterengineering": (
        "better_engineering",
        "Better Engineering",
        "industry",
        10000,
    ),
    "cheapermaterials": ("cheaper_materials", "Cheaper Materials", "industry", 8000),
    "onlineshopping": ("online_shopping", "Online Shopping", "infrastructure", 12000),
    "governmentregulation": (
        "government_regulation",
        "Government Regulation",
        "diplomacy",
        15000,
    ),
    "nationalhealthinstitution": (
        "national_health_institution",
        "National Health Institution",
        "science",
        20000,
    ),
    "highspeedrail": ("high_speed_rail", "High Speed Rail", "infrastructure", 25000),
    "advancedmachinery": (
        "advanced_machinery",
        "Advanced Machinery",
        "industry",
        18000,
    ),
    "strongerexplosives": (
        "stronger_explosives",
        "Stronger Explosives",
        "military",
        15000,
    ),
    "widespreadpropaganda": (
        "widespread_propaganda",
        "Widespread Propaganda",
        "diplomacy",
        10000,
    ),
    "increasedfunding": ("increased_funding", "Increased Funding", "science", 12000),
    "automationintegration": (
        "automation_integration",
        "Automation Integration",
        "industry",
        30000,
    ),
    "largerforges": ("larger_forges", "Larger Forges", "industry", 14000),
    "lootingteams": ("looting_teams", "Looting Teams", "military", 8000),
    "organizedsupplylines": (
        "organized_supply_lines",
        "Organized Supply Lines",
        "military",
        16000,
    ),
    "largestorehouses": (
        "large_storehouses",
        "Large Storehouses",
        "infrastructure",
        11000,
    ),
    "ballisticmissilesilo": (
        "ballistic_missile_silo",
        "Ballistic Missile Silo",
        "military",
        40000,
    ),
    "icbmsilo": ("icbm_silo", "ICBM Silo", "military", 50000),
    "nucleartestingfacility": (
        "nuclear_testing_facility",
        "Nuclear Testing Facility",
        "military",
        60000,
    ),
}


def ensure_all_techs_exist(conn):
    """
    Ensure all legacy tech columns have corresponding entries in tech_dictionary
    Returns dict mapping normalized names to tech_ids
    """
    print("\n" + "=" * 70)
    print("STEP 1: ENSURE ALL TECHS EXIST IN DICTIONARY")
    print("=" * 70)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Get existing techs
    cursor.execute("SELECT tech_id, name FROM tech_dictionary")
    existing_techs = {row["name"]: row["tech_id"] for row in cursor.fetchall()}
    print(f"\n✓ Found {len(existing_techs)} existing techs in dictionary")

    # Insert missing techs
    new_techs = []
    for _legacy_col, (
        norm_name,
        display,
        category,
        cost,
    ) in LEGACY_TECH_MAPPINGS.items():
        if norm_name not in existing_techs:
            new_techs.append((norm_name, display, category, cost))

    if new_techs:
        print(f"\n📝 Adding {len(new_techs)} new techs to dictionary...")
        insert_query = """
            INSERT INTO tech_dictionary
            (name, display_name, category, research_cost, prerequisite_tech_id)
            VALUES (%s, %s, %s, %s, NULL)
            ON CONFLICT (name) DO NOTHING
            RETURNING tech_id, name
        """
        for tech in new_techs:
            cursor.execute(insert_query, tech)
            result = cursor.fetchone()
            if result:
                print(f"  • Added: {tech[1]} ({tech[2]})")

        conn.commit()
        print(f"✓ Successfully added {len(new_techs)} new techs")
    else:
        print("\n✓ All techs already exist in dictionary")

    # Refresh tech lookup
    cursor.execute("SELECT tech_id, name FROM tech_dictionary")
    tech_lookup = {row["name"]: row["tech_id"] for row in cursor.fetchall()}

    cursor.close()
    return tech_lookup


def migrate_all_tech_data(conn, tech_lookup):
    """
    Migrate ALL legacy tech data from upgrades table to user_tech
    """
    print("\n" + "=" * 70)
    print("STEP 2: MIGRATE ALL TECH DATA")
    print("=" * 70)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Read all upgrades data joined with valid users
    print("\n[1/4] Reading legacy upgrades table...")
    cursor.execute(
        """
        SELECT up.*
        FROM upgrades up
        INNER JOIN users u ON up.user_id = u.id
    """
    )
    upgrade_rows = cursor.fetchall()
    print(f"✓ Found {len(upgrade_rows)} users with valid upgrade data")

    # Prepare migration data for ALL columns
    print("\n[2/4] Processing all upgrade columns...")
    migration_data = []
    tech_counts = {}

    for row in upgrade_rows:
        user_id = row["user_id"]

        for _legacy_col, (norm_name, _, _, _) in LEGACY_TECH_MAPPINGS.items():
            # Check if this upgrade is unlocked
            is_unlocked = (row.get(_legacy_col) or 0) > 0
            if not is_unlocked:
                continue

            # Look up tech_id
            tech_id = tech_lookup.get(norm_name)
            if tech_id is None:
                print(f"⚠ Warning: Tech '{norm_name}' not found in dictionary")
                continue

            migration_data.append((user_id, tech_id, True))
            tech_counts[norm_name] = tech_counts.get(norm_name, 0) + 1

    print(f"✓ Prepared {len(migration_data):,} tech unlock records")

    # Show breakdown
    if tech_counts:
        print("\n📊 Tech unlock breakdown:")
        for tech_name, count in sorted(
            tech_counts.items(), key=lambda x: x[1], reverse=True
        ):
            if count > 0:
                print(f"  • {tech_name}: {count} users")

    # Insert into user_tech
    print("\n[3/4] Inserting into user_tech table...")
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
        print("⚠ No tech data to migrate")

    cursor.close()
    return len(migration_data), tech_counts


def verify_tech_migration(conn):
    """Verify the tech migration was successful"""
    print("\n" + "=" * 70)
    print("STEP 3: VERIFICATION")
    print("=" * 70)

    cursor = conn.cursor(cursor_factory=RealDictCursor)

    # Count total techs in dictionary
    cursor.execute("SELECT COUNT(*) as count FROM tech_dictionary")
    dict_count = cursor.fetchone()["count"]
    print(f"\n✓ Total techs in dictionary: {dict_count}")

    # Count user tech records
    cursor.execute(
        """
        SELECT
            COUNT(*) as total_records,
            SUM(CASE WHEN is_unlocked THEN 1 ELSE 0 END) as unlocked_count,
            COUNT(DISTINCT user_id) as unique_users
        FROM user_tech
    """
    )
    result = cursor.fetchone()
    print(f"✓ Total user_tech records: {result['total_records']:,}")
    unlocked = result["unlocked_count"] or 0
    print(f"✓ Unlocked techs: {unlocked:,}")
    print(f"✓ Unique users with tech progress: {result['unique_users']:,}")

    # Top techs
    print("\n📊 Most researched techs:")
    cursor.execute(
        """
        SELECT td.display_name, COUNT(*) as unlock_count
        FROM user_tech ut
        JOIN tech_dictionary td ON ut.tech_id = td.tech_id
        WHERE ut.is_unlocked = TRUE
        GROUP BY td.display_name
        ORDER BY unlock_count DESC
        LIMIT 10
    """
    )
    for row in cursor.fetchall():
        print(f"  • {row['display_name']}: {row['unlock_count']} users")

    cursor.close()


def main():
    print("=" * 70)
    print("COMPLETE TECH MIGRATION: Legacy Upgrades → Normalized Tech Tree")
    print("=" * 70)

    try:
        conn = get_db_connection()
        print("\n✓ Database connection established")

        # Step 1: Ensure all techs exist
        tech_lookup = ensure_all_techs_exist(conn)

        # Step 2: Migrate all tech data
        migrated_count, tech_counts = migrate_all_tech_data(conn, tech_lookup)

        # Step 3: Verify
        verify_tech_migration(conn)

        # Summary
        print("\n" + "=" * 70)
        print("MIGRATION COMPLETE")
        print("=" * 70)
        print(f"\n✓ Total tech records migrated: {migrated_count:,}")
        print(f"✓ Unique techs with data: {len(tech_counts)}")
        print("\n⚠ Legacy 'upgrades' table NOT deleted - verify in DBeaver")
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
