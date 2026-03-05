#!/usr/bin/env python3
"""Backfill Economy 2.0 normalized tables for all existing users.

Inserts rows into user_economy, user_buildings, and user_military for any
user who is missing them.  Uses ON CONFLICT DO NOTHING so the script is
safe to run repeatedly (idempotent).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_connection  # noqa: E402


def backfill():
    with get_db_connection() as conn:
        cur = conn.cursor()
    try:
        # 1. user_economy — one row per (user, resource) pair
        cur.execute(
            """
            INSERT INTO user_economy (user_id, resource_id, quantity)
            SELECT u.id, rd.resource_id, 0
            FROM users u
            CROSS JOIN resource_dictionary rd
            LEFT JOIN user_economy ue
                ON ue.user_id = u.id AND ue.resource_id = rd.resource_id
            WHERE ue.user_id IS NULL
            ON CONFLICT DO NOTHING
        """
        )
        economy_rows = cur.rowcount
        print(f"user_economy: inserted {economy_rows} rows")

        # 2. user_buildings — one row per (user, active building) pair
        cur.execute(
            """
            INSERT INTO user_buildings (user_id, building_id, quantity)
            SELECT u.id, bd.building_id, 0
            FROM users u
            CROSS JOIN building_dictionary bd
            LEFT JOIN user_buildings ub
                ON ub.user_id = u.id AND ub.building_id = bd.building_id
            WHERE ub.user_id IS NULL
              AND bd.is_active = TRUE
            ON CONFLICT DO NOTHING
        """
        )
        buildings_rows = cur.rowcount
        print(f"user_buildings: inserted {buildings_rows} rows")

        # 3. user_military — one row per (user, active unit) pair
        cur.execute(
            """
            INSERT INTO user_military (user_id, unit_id, quantity)
            SELECT u.id, ud.unit_id, 0
            FROM users u
            CROSS JOIN unit_dictionary ud
            LEFT JOIN user_military um
                ON um.user_id = u.id AND um.unit_id = ud.unit_id
            WHERE um.user_id IS NULL
              AND ud.is_active = TRUE
            ON CONFLICT DO NOTHING
        """
        )
        military_rows = cur.rowcount
        print(f"user_military: inserted {military_rows} rows")

        conn.commit()
        print("Backfill complete — all rows committed.")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        cur.close()


if __name__ == "__main__":
    backfill()
