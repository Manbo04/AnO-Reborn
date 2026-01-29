#!/usr/bin/env python3
"""
Migration script to add email verification columns to users table.

Run: python scripts/add_email_verification_columns.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection


def migrate():
    """Add is_verified and verification_token columns to users table"""
    with get_db_connection() as conn:
        cur = conn.cursor()

        try:
            print("Adding is_verified column to users table...")
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS is_verified BOOLEAN DEFAULT FALSE;
            """
            )

            print("Adding verification_token column to users table...")
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS verification_token TEXT;
            """
            )

            print("Adding token_created_at column for expiry tracking...")
            cur.execute(
                """
                ALTER TABLE users
                ADD COLUMN IF NOT EXISTS token_created_at TIMESTAMP;
            """
            )

            # Mark all existing users as verified (they signed up before this system)
            print("Marking existing users as verified...")
            cur.execute(
                """
                UPDATE users SET is_verified = TRUE WHERE is_verified IS NULL OR is_verified = FALSE;
            """
            )

            conn.commit()
            print("✓ Migration complete! Email verification columns added.")
            print("✓ All existing users marked as verified.")

        except Exception as e:
            conn.rollback()
            print(f"✗ Error during migration: {e}")
            raise
        finally:
            cur.close()


if __name__ == "__main__":
    migrate()
