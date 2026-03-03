#!/usr/bin/env python3
"""
Admin Script: Grant Starter Military Units to Test User
Purpose: Repopulate military units after database migration/recovery
Usage: python3 grant_starter_army.py [user_id]
"""

import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

# Starter army composition (unit_name -> quantity)
STARTER_ARMY = {
    "soldiers": 100,
    "tanks": 10,
    "fighters": 5,
    "artillery": 8,
    "destroyers": 3,
}


def grant_starter_army(user_id):
    """Grant a starter army to a user by populating user_military."""
    conn = None
    try:
        conn = psycopg2.connect(DATABASE_URL)
        db = conn.cursor()

        # Get unit IDs from unit_dictionary
        unit_ids = {}
        db.execute(
            "SELECT unit_id, name FROM unit_dictionary WHERE name = ANY(%s)",
            (list(STARTER_ARMY.keys()),),
        )
        for unit_id, unit_name in db.fetchall():
            unit_ids[unit_name] = unit_id

        if len(unit_ids) != len(STARTER_ARMY):
            missing = set(STARTER_ARMY.keys()) - set(unit_ids.keys())
            print(f"ERROR: Missing units in database: {missing}")
            return False

        # Insert or update user_military entries
        for unit_name, quantity in STARTER_ARMY.items():
            unit_id = unit_ids[unit_name]
            db.execute(
                """
                INSERT INTO user_military (user_id, unit_id, quantity, updated_at)
                VALUES (%s, %s, %s, now())
                ON CONFLICT (user_id, unit_id)
                DO UPDATE SET quantity = EXCLUDED.quantity, updated_at = now()
                """,
                (user_id, unit_id, quantity),
            )
            print(f"✓ Granted {quantity}x {unit_name} (unit_id={unit_id})")

        conn.commit()
        print(f"\n✅ Starter army granted to user {user_id}")
        return True

    except Exception as e:
        print(f"ERROR: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # Default: Dede's user ID
        user_id = 1
        print(f"No user ID provided, using default: {user_id} (Dede)")
    else:
        try:
            user_id = int(sys.argv[1])
        except ValueError:
            print(f"ERROR: Invalid user ID: {sys.argv[1]}")
            sys.exit(1)

    success = grant_starter_army(user_id)
    sys.exit(0 if success else 1)
