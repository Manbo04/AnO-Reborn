"""
Migration 012: Add province_id to user_buildings

The user_buildings table was created per-user (user_id, building_id) but
buildings should be per-province.  The old proinfra table was per-province;
when it was normalized into user_buildings the province association was lost.

This migration:
1. Adds province_id column to user_buildings
2. Assigns existing building rows to each user's FIRST province
3. Makes province_id NOT NULL
4. Replaces the PK with (user_id, building_id, province_id)
5. Adds FK to provinces.id
6. Adds index on province_id
"""

import os
import sys

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: No DATABASE_PUBLIC_URL or DATABASE_URL found in environment.")
    sys.exit(1)


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    dcur = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # ── Step 0: Check if already migrated ────────────────────────
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'user_buildings' AND column_name = 'province_id'
        """)
        if cur.fetchone():
            print("province_id column already exists — skipping migration.")
            return

        # ── Step 1: Add province_id column (nullable for now) ────────
        print("[1/6] Adding province_id column...")
        cur.execute("ALTER TABLE user_buildings ADD COLUMN province_id INT")

        # ── Step 2: Assign existing rows to first province per user ──
        print("[2/6] Assigning buildings to first province per user...")
        # Get first province for each user (lowest id)
        dcur.execute("""
            SELECT userid AS user_id, MIN(id) AS first_province_id
            FROM provinces
            GROUP BY userid
        """)
        first_provinces = {
            row["user_id"]: row["first_province_id"]
            for row in dcur.fetchall()
        }

        # Get all user_ids that have buildings
        cur.execute("SELECT DISTINCT user_id FROM user_buildings")
        building_users = [row[0] for row in cur.fetchall()]

        updated = 0
        orphaned = 0
        for uid in building_users:
            first_prov = first_provinces.get(uid)
            if first_prov:
                cur.execute(
                    "UPDATE user_buildings SET province_id = %s WHERE user_id = %s",
                    (first_prov, uid),
                )
                updated += cur.rowcount
            else:
                # User has buildings but no provinces — delete orphaned rows
                cur.execute(
                    "DELETE FROM user_buildings WHERE user_id = %s",
                    (uid,),
                )
                orphaned += cur.rowcount

        print(f"    Assigned {updated} rows, deleted {orphaned} orphaned rows.")

        # ── Step 3: Make province_id NOT NULL ────────────────────────
        print("[3/6] Making province_id NOT NULL...")
        cur.execute(
            "ALTER TABLE user_buildings ALTER COLUMN province_id SET NOT NULL"
        )

        # ── Step 4: Replace PK ───────────────────────────────────────
        print("[4/6] Replacing primary key...")
        cur.execute("ALTER TABLE user_buildings DROP CONSTRAINT user_buildings_pkey")
        cur.execute(
            "ALTER TABLE user_buildings ADD PRIMARY KEY "
            "(user_id, building_id, province_id)"
        )

        # ── Step 5: Add FK ───────────────────────────────────────────
        print("[5/6] Adding foreign key to provinces...")
        cur.execute("""
            ALTER TABLE user_buildings
            ADD CONSTRAINT fk_user_buildings_province
            FOREIGN KEY (province_id) REFERENCES provinces(id) ON DELETE CASCADE
        """)

        # ── Step 6: Add indexes ──────────────────────────────────────
        print("[6/6] Adding indexes...")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_buildings_province_id "
            "ON user_buildings(province_id)"
        )
        # Update existing composite index to include province_id
        cur.execute(
            "DROP INDEX IF EXISTS idx_user_buildings_user_building"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_buildings_user_building_province "
            "ON user_buildings(user_id, building_id, province_id)"
        )

        conn.commit()
        print("Migration 012 complete.")

    except Exception as e:
        conn.rollback()
        print(f"Migration failed, rolled back: {e}")
        raise
    finally:
        cur.close()
        dcur.close()
        conn.close()


if __name__ == "__main__":
    run()
