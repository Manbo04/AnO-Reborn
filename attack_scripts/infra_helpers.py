"""Infrastructure helpers extracted from `Nations.py`/`Military`.

Provides a small, testable wrapper around the SQL aggregation used by
`Military.get_limits` so we can test and reuse it during refactor.
"""

from typing import Tuple

from database import get_db_cursor


def aggregate_proinfra_for_user(cId: int) -> Tuple[int, int, int, int, int]:
    """Return aggregated building counts for a user's military buildings.

    Uses the normalized user_buildings + building_dictionary tables.
    Returns (army_bases, harbours, aerodomes, admin_buildings, silos).

    Note: admin_buildings and silos are not in building_dictionary yet,
    so they default to 0 until added.
    """
    building_names = [
        "army_bases",
        "harbours",
        "aerodromes",
        "admin_buildings",
        "silos",
    ]

    with get_db_cursor() as db:
        db.execute(
            """SELECT bd.name, COALESCE(ub.quantity, 0) AS quantity
               FROM building_dictionary bd
               LEFT JOIN user_buildings ub
                   ON ub.building_id = bd.building_id AND ub.user_id = %s
               WHERE bd.name = ANY(%s) AND bd.is_active = TRUE""",
            (cId, building_names),
        )
        rows = db.fetchall()

        counts = {name: 0 for name in building_names}
        for row in rows:
            counts[row[0]] = int(row[1]) if row[1] is not None else 0

        # Handle aerodomes/aerodromes naming inconsistency
        aerodomes = counts.get("aerodromes", 0) or counts.get("aerodomes", 0)

        return (
            counts.get("army_bases", 0),
            counts.get("harbours", 0),
            aerodomes,
            counts.get("admin_buildings", 0),
            counts.get("silos", 0),
        )
