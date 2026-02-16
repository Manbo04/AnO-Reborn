"""Infrastructure/`proInfra` helpers extracted from `Nations.py`/`Military`.

Provides a small, testable wrapper around the SQL aggregation used by
`Military.get_limits` so we can test and reuse it during refactor.
"""
from typing import Tuple

from database import get_db_cursor


def aggregate_proinfra_for_user(cId: int) -> Tuple[int, int, int, int, int]:
    """Return aggregated proInfra counts for a user's provinces.

    Returns (army_bases, harbours, aerodomes, admin_buildings, silos).
    """
    with get_db_cursor() as db:
        db.execute(
            """SELECT
                COALESCE(SUM(pi.army_bases), 0) as army_bases,
                COALESCE(SUM(pi.harbours), 0) as harbours,
                COALESCE(SUM(pi.aerodomes), 0) as aerodomes,
                COALESCE(SUM(pi.admin_buildings), 0) as admin_buildings,
                COALESCE(SUM(pi.silos), 0) as silos
            FROM proinfra pi
            INNER JOIN provinces p ON pi.id = p.id
            WHERE p.userID=%s""",
            (cId,),
        )
        row = db.fetchone()
        if not row:
            return 0, 0, 0, 0, 0
        return tuple(int(x or 0) for x in row)
