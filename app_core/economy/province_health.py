"""One-screen province health table for the nation overview (celess mob's
"UI Improvements" suggestion): per-province power, slot use and stability,
worst provinces first, so problems can be fixed without opening each province.
"""

import logging

from database import get_request_cursor
from app_core.economy.building_costs import CITY_UNITS, LAND_UNITS
from app_core.economy.province_power import nation_province_power

logger = logging.getLogger(__name__)


def _stability(happiness) -> str:
    # Same thresholds as the Provinces list on the overview page.
    h = happiness or 0
    if h >= 60:
        return "stable"
    if h >= 35:
        return "unrest"
    return "threat"


def nation_province_health(user_id: int, rows: list) -> dict:
    """``rows`` are the overview's province tuples:
    (name, id, population, cityCount, land, happiness, productivity, ...).

    Returns {"rows": [...worst first...], "unpowered": n, "unstable": n,
    "city_used", "city_total", "land_used", "land_total", "power_used",
    "power_total"}. Never raises: the overview must render without it.
    """
    empty = {"rows": [], "unpowered": 0, "unstable": 0, "city_used": 0, "city_total": 0,
             "land_used": 0, "land_total": 0, "power_used": 0, "power_total": 0}
    if not rows:
        return empty
    try:
        ids = [r[1] for r in rows]
        used = {}
        with get_request_cursor(read_only=True) as db:
            db.execute(
                """
                SELECT ub.province_id,
                       COALESCE(SUM(ub.quantity) FILTER (WHERE bd.name = ANY(%s)), 0),
                       COALESCE(SUM(ub.quantity) FILTER (WHERE bd.name = ANY(%s)), 0)
                FROM user_buildings ub
                JOIN building_dictionary bd ON bd.building_id = ub.building_id
                WHERE ub.user_id = %s AND ub.province_id = ANY(%s)
                GROUP BY ub.province_id
                """,
                (list(CITY_UNITS), list(LAND_UNITS), user_id, ids),
            )
            for pid, c, l in db.fetchall():
                used[pid] = (int(c), int(l))

        power = nation_province_power(
            user_id, [{"id": r[1], "productivity": r[6]} for r in rows]
        )

        out = dict(empty)
        table = []
        for r in rows:
            pid, happiness = r[1], r[5]
            city_used, land_used = used.get(pid, (0, 0))
            energy = power.get(pid) or {}
            powered = bool(energy.get("has_power", True))
            stability = _stability(happiness)
            table.append({
                "id": pid, "name": r[0], "population": r[2],
                "city_used": city_used, "city_total": int(r[3] or 0),
                "land_used": land_used, "land_total": int(r[4] or 0),
                "power_used": int(energy.get("consumption", 0) or 0),
                "power_total": int(energy.get("production", 0) or 0),
                "powered": powered, "stability": stability, "happiness": happiness or 0,
            })
        for t in table:
            out["city_used"] += t["city_used"]; out["city_total"] += t["city_total"]
            out["land_used"] += t["land_used"]; out["land_total"] += t["land_total"]
            out["power_used"] += t["power_used"]; out["power_total"] += t["power_total"]
            out["unpowered"] += 0 if t["powered"] else 1
            out["unstable"] += 0 if t["stability"] == "stable" else 1
        # Worst first: unpowered, then lowest happiness; name keeps ties stable.
        table.sort(key=lambda t: (t["powered"], t["happiness"], str(t["name"])))
        out["rows"] = table
        return out
    except Exception:
        logger.exception("nation_province_health failed for user %s", user_id)
        return empty
