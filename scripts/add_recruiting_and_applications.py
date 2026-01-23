#!/usr/bin/env python3
"""Migration: add `recruiting` flag to colNames and create col_applications table

Run: python scripts/add_recruiting_and_applications.py
"""
from database import get_db_connection

if __name__ == "__main__":
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            print("Adding 'recruiting' column to colNames if missing...")
            cur.execute(
                """
                ALTER TABLE colNames
                ADD COLUMN IF NOT EXISTS recruiting BOOLEAN DEFAULT FALSE;
                """
            )

            print("Creating col_applications table if missing...")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS col_applications (
                    id SERIAL PRIMARY KEY,
                    colId INTEGER NOT NULL,
                    userId INTEGER NOT NULL,
                    message TEXT,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
                );
                """
            )

            conn.commit()
            print("✓ Migration complete")
        except Exception as e:
            conn.rollback()
            print("✗ Migration failed:", e)
            raise
        finally:
            cur.close()
