"""Insert missing rows for resources, stats, and military for any users missing them.

This uses the same DEFAULTS values as `reset_progress.py`.
"""

from database import get_db_cursor

DEFAULTS = {
    "rations": 10000,
    "lumber": 2000,
    "steel": 2000,
    "aluminium": 2000,
    "gold": 100000000,
    "military_manpower": 100,
    "defcon": 1,
    "raw_start": 500,
}

with get_db_cursor() as db:
    # Find users missing resources
    db.execute(
        "SELECT u.id, u.username FROM users u "
        "LEFT JOIN resources r ON u.id=r.id WHERE r.id IS NULL"
    )
    missing_res = db.fetchall()
    if missing_res:
        print("Inserting resources for users:", missing_res)
        for uid, _uname in missing_res:
            db.execute(
                (
                    "INSERT INTO resources (id, rations, lumber, steel, aluminium, "
                    "oil, coal, uranium, bauxite, lead, copper, iron, components) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                ),
                (
                    uid,
                    DEFAULTS["rations"],
                    DEFAULTS["lumber"],
                    DEFAULTS["steel"],
                    DEFAULTS["aluminium"],
                    DEFAULTS["raw_start"],
                    DEFAULTS["raw_start"],
                    DEFAULTS["raw_start"],
                    DEFAULTS["raw_start"],
                    DEFAULTS["raw_start"],
                    DEFAULTS["raw_start"],
                    DEFAULTS["raw_start"],
                    DEFAULTS["raw_start"],
                ),
            )
    else:
        print("No missing resources rows")

    # Find users missing stats
    db.execute(
        "SELECT u.id, u.username FROM users u "
        "LEFT JOIN stats s ON u.id=s.id WHERE s.id IS NULL"
    )
    missing_stats = db.fetchall()
    if missing_stats:
        print("Inserting stats for users:", missing_stats)
        for uid, _uname in missing_stats:
            # stats.location is NOT NULL in this schema; use empty string default
            db.execute(
                "INSERT INTO stats (id, location, gold) VALUES (%s,%s,%s)",
                (uid, "", DEFAULTS["gold"]),
            )
    else:
        print("No missing stats rows")

    # Find users missing military
    db.execute(
        "SELECT u.id, u.username FROM users u "
        "LEFT JOIN military m ON u.id=m.id WHERE m.id IS NULL"
    )
    missing_mil = db.fetchall()
    if missing_mil:
        print("Inserting military for users:", missing_mil)
        for uid, _uname in missing_mil:
            db.execute(
                (
                    "INSERT INTO military (id, manpower, defcon, soldiers, "
                    "artillery, tanks, bombers, fighters, apaches, spies, ICBMs, "
                    "nukes, destroyers, cruisers, submarines) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                ),
                (
                    uid,
                    DEFAULTS["military_manpower"],
                    DEFAULTS["defcon"],
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                ),
            )
    else:
        print("No missing military rows")

print("Fixes applied")
