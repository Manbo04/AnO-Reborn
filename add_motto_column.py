#!/usr/bin/env python3
"""
Database migration script to add motto column to users table.
Run this script once to add the motto field support.
"""

import psycopg2
from database import get_db_connection


def add_motto_column():
    """Add motto column to users table if it doesn't exist."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the column already exists
        cursor.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name='users' AND column_name='motto';
        """
        )

        if cursor.fetchone():
            print("✓ Motto column already exists in users table")
            cursor.close()
            conn.close()
            return

        # Add the motto column
        print("Adding motto column to users table...")
        cursor.execute(
            """
            ALTER TABLE users
            ADD COLUMN motto VARCHAR(100) DEFAULT NULL;
        """
        )

        conn.commit()
        print("✓ Successfully added motto column to users table")

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print(f"✗ Database error: {e}")
        if conn:
            conn.rollback()
            conn.close()
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    print("Running database migration: Add motto column")
    add_motto_column()
    print("Migration complete!")
