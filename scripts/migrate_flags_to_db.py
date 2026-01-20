#!/usr/bin/env python3
"""
Migration script to add flag_data columns to store flag images in PostgreSQL.
This provides persistent flag storage that survives Railway deployments.

Run: python scripts/migrate_flags_to_db.py
"""
import os
import sys
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection


def migrate():
    """Add flag_data columns to users and colNames tables"""
    with get_db_connection() as conn:
        cur = conn.cursor()

        try:
            # Add flag_data column to users table (for country flags)
            print("Adding flag_data column to users table...")
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS flag_data TEXT;
            """
            )

            # Add flag_data column to colNames table (for coalition flags)
            print("Adding flag_data column to colNames table...")
            cur.execute(
                """
                ALTER TABLE colNames
                ADD COLUMN IF NOT EXISTS flag_data TEXT;
            """
            )

            conn.commit()
            print("✓ Migration complete! flag_data columns added.")

            # Try to migrate existing local files to database
            migrate_existing_flags(cur, conn)

        except Exception as e:
            conn.rollback()
            print(f"✗ Error during migration: {e}")
            raise
        finally:
            cur.close()


def migrate_existing_flags(cur, conn):
    """Migrate any existing local flag files to database"""
    flags_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "flags"
    )

    if not os.path.exists(flags_dir):
        print("No flags directory found, skipping file migration")
        return

    migrated = 0

    # Migrate country flags (flag_<user_id>.*)
    cur.execute("SELECT id, flag FROM users WHERE flag IS NOT NULL AND flag != ''")
    users = cur.fetchall()

    for user_id, flag_filename in users:
        flag_path = os.path.join(flags_dir, flag_filename)
        if os.path.exists(flag_path) and os.path.getsize(flag_path) > 0:
            try:
                with open(flag_path, "rb") as f:
                    flag_data = base64.b64encode(f.read()).decode("utf-8")
                cur.execute(
                    "UPDATE users SET flag_data = %s WHERE id = %s",
                    (flag_data, user_id),
                )
                migrated += 1
                print(f"  Migrated user flag: {flag_filename}")
            except Exception as e:
                print(f"  Failed to migrate {flag_filename}: {e}")

    # Migrate coalition flags (col_flag_<coalition_id>.*)
    cur.execute("SELECT id, flag FROM colNames WHERE flag IS NOT NULL AND flag != ''")
    coalitions = cur.fetchall()

    for col_id, flag_filename in coalitions:
        flag_path = os.path.join(flags_dir, flag_filename)
        if os.path.exists(flag_path) and os.path.getsize(flag_path) > 0:
            try:
                with open(flag_path, "rb") as f:
                    flag_data = base64.b64encode(f.read()).decode("utf-8")
                cur.execute(
                    "UPDATE colNames SET flag_data = %s WHERE id = %s",
                    (flag_data, col_id),
                )
                migrated += 1
                print(f"  Migrated coalition flag: {flag_filename}")
            except Exception as e:
                print(f"  Failed to migrate {flag_filename}: {e}")

    conn.commit()
    print(f"✓ Migrated {migrated} existing flag files to database")


if __name__ == "__main__":
    migrate()
