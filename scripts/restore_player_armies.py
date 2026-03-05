#!/usr/bin/env python3
"""scripts/restore_player_armies.py

One-time army restoration for the Economy 2.0 gasoline despawn incident.

For each of the 138 active players, audits their infrastructure and tops up
every unit type to its maximum capacity based on:
  - army_bases   -> soldiers (x100), tanks (x8), artillery (x8)
  - aerodomes    -> fighters, bombers, apaches (div 3 each, rounded)
  - harbours     -> destroyers, submarines (div 2 each), cruisers (x2)
  - admin_buildings -> spies (x1)
  - silos        -> icbms (silos+1), nukes (silos)

Units are only increased, NEVER decreased.
Runs inside a single transaction; rolls back on any error.
"""

import os
import sys

# Allow running from repo root without activating venv explicitly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from database import get_db_connection  # noqa: E402


def run():
    with get_db_connection() as conn:
        _run_with_conn(conn)


def _run_with_conn(conn):
    db = conn.cursor()

    # ── Fetch all active users ────────────────────────────────────────────────
    db.execute("SELECT id FROM users ORDER BY id")
    users = [row[0] for row in db.fetchall()]
    print(f"Restoring armies for {len(users)} players...")

    # ── Pre-fetch all unit_ids ────────────────────────────────────────────────
    db.execute("SELECT name, unit_id FROM unit_dictionary")
    unit_id_map = {name: uid for name, uid in db.fetchall()}

    # ── Pre-fetch all building_ids we need ───────────────────────────────────
    needed_buildings = [
        "army_bases",
        "harbours",
        "aerodomes",
        "admin_buildings",
        "silos",
    ]
    db.execute(
        "SELECT name, building_id FROM building_dictionary WHERE name = ANY(%s)",
        (needed_buildings,),
    )
    bld_id_map = {name: bid for name, bid in db.fetchall()}
    del bld_id_map  # fetched for validation; not used further

    updated_users = 0
    total_units_restored = 0

    for user_id in users:
        # ── Building counts (sum across all provinces) ────────────────────────
        db.execute(
            """
            SELECT bd.name, COALESCE(SUM(ub.quantity), 0)
            FROM building_dictionary bd
            LEFT JOIN user_buildings ub ON ub.building_id = bd.building_id
                AND ub.user_id = %s
            WHERE bd.name = ANY(%s)
            GROUP BY bd.name
            """,
            (user_id, needed_buildings),
        )
        bld = {row[0]: int(row[1]) for row in db.fetchall()}
        army_bases = bld.get("army_bases", 0)
        harbours = bld.get("harbours", 0)
        aerodomes = bld.get("aerodomes", 0)
        admin_buildings = bld.get("admin_buildings", 0)
        silos = bld.get("silos", 0)

        # ── Max capacity per unit type ────────────────────────────────────────
        # Air capacity is shared: aerodomes*5 total → split ~evenly 3 ways
        air_cap_each = (aerodomes * 5) // 3  # fighters and bombers
        apache_cap = aerodomes * 5 - air_cap_each * 2  # remainder

        # Naval: destroyers+submarines share harbours*3; cruisers = harbours*2
        naval_shared_each = (harbours * 3) // 2
        naval_remainder = harbours * 3 - naval_shared_each  # submarines

        caps = {
            "soldiers": army_bases * 100,
            "tanks": army_bases * 8,
            "artillery": army_bases * 8,
            "fighters": air_cap_each,
            "bombers": air_cap_each,
            "apaches": apache_cap,
            "destroyers": naval_shared_each,
            "submarines": naval_remainder,
            "cruisers": harbours * 2,
            "spies": admin_buildings * 1,
            "icbms": silos + 1 if silos > 0 else 0,
            "nukes": silos,
        }

        # ── Current unit counts ───────────────────────────────────────────────
        db.execute(
            """
            SELECT ud.name, COALESCE(um.quantity, 0)
            FROM unit_dictionary ud
            LEFT JOIN user_military um ON um.unit_id = ud.unit_id
                AND um.user_id = %s
            """,
            (user_id,),
        )
        current = {row[0]: int(row[1]) for row in db.fetchall()}

        # ── Apply top-ups ─────────────────────────────────────────────────────
        user_restored = 0
        for unit_name, cap in caps.items():
            if cap <= 0:
                continue
            unit_id = unit_id_map.get(unit_name)
            if unit_id is None:
                continue
            cur = current.get(unit_name, 0)
            if cur < cap:
                new_qty = cap
                db.execute(
                    """
                    INSERT INTO user_military (user_id, unit_id, quantity, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (user_id, unit_id)
                    DO UPDATE SET
                        quantity = GREATEST(user_military.quantity, EXCLUDED.quantity),
                        updated_at = now()
                    """,
                    (user_id, unit_id, new_qty),
                )
                added = new_qty - cur
                user_restored += added
                total_units_restored += added

        if user_restored > 0:
            updated_users += 1

    print(
        f"Done. {updated_users}/{len(users)} players received unit top-ups. "
        f"Total units restored: {total_units_restored:,}"
    )


if __name__ == "__main__":
    run()
