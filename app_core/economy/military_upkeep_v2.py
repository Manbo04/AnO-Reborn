"""Military upkeep v2 (Dede, 2026-11-05, from #military-recommendations).

Numbers are per unit, per GAME YEAR (24 hourly ticks = 1 year, i.e. 24h IRL).
Each tick charges 1/24 of them, rounded up per nation and resource. ``money``
is gold, everything else is a resource name from resource_dictionary. Units not listed here keep the legacy
single-resource upkeep in unit_dictionary. Nothing is charged before
UPKEEP_V2_START (24h grace period after the announcement).
"""

import math
from datetime import datetime, timezone

UPKEEP_V2_START = datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc)

TICKS_PER_YEAR = 24

UPKEEP_V2 = {  # per unit, per game year
    "soldiers": {"money": 75_000, "rations": 1},
    "artillery": {"ammunition": 1, "money": 38_000_000},
    "tanks": {"gasoline": 1, "ammunition": 1, "steel": 2, "money": 45_000_000},
    "apaches": {"gasoline": 1, "ammunition": 1, "aluminium": 1, "money": 175_000_000},
    "bombers": {"gasoline": 3, "ammunition": 4, "aluminium": 4, "money": 1_200_000_000},
    "fighters": {"gasoline": 2, "ammunition": 2, "aluminium": 2, "money": 750_000_000},
    "submarines": {"uranium": 2, "ammunition": 10, "steel": 10, "money": 1_000_000_000},
    "destroyers": {"gasoline": 10, "ammunition": 5, "steel": 15, "money": 1_200_000_000},
    "cruisers": {"gasoline": 20, "ammunition": 15, "steel": 20, "money": 2_000_000_000},
    "aircraft_carriers": {
        "uranium": 10,
        "gasoline": 5,
        "ammunition": 30,
        "steel": 40,
        "money": 5_000_000_000,
    },
}


def v2_active(now=None):
    return (now or datetime.now(timezone.utc)) >= UPKEEP_V2_START


def v2_unit_names():
    return list(UPKEEP_V2)


def describe(unit_name):
    """Annual cost, e.g. '75,000 money, 1 rations' (per year), for a unit, or '' if it has no v2 entry."""
    costs = UPKEEP_V2.get(unit_name)
    if not costs:
        return ""
    return ", ".join(f"{amt:,} {res}" for res, amt in costs.items())


def _dict_rows(cursor):
    cols = [c[0] for c in cursor.description]
    return [r if isinstance(r, dict) else dict(zip(cols, r)) for r in cursor.fetchall()]


def v2_rows(cursor, user_id=None):
    """(user_id, resource_id|None, resource, required_amount); money has resource_id None."""
    cursor.execute(
        """
        SELECT um.user_id, ud.name AS unit, um.quantity
        FROM user_military um
        JOIN unit_dictionary ud ON ud.unit_id = um.unit_id
        WHERE um.quantity > 0 AND ud.name = ANY(%(names)s)
          AND (%(uid)s::int IS NULL OR um.user_id = %(uid)s::int)
        """,
        {"names": v2_unit_names(), "uid": user_id},
    )
    units = _dict_rows(cursor)
    cursor.execute("SELECT resource_id, name FROM resource_dictionary")
    ids = {r["name"]: r["resource_id"] for r in _dict_rows(cursor)}
    totals = {}
    for u in units:
        for res, amt in UPKEEP_V2[u["unit"]].items():
            key = (u["user_id"], res)
            totals[key] = totals.get(key, 0) + int(u["quantity"]) * amt
    return [
        {
            "user_id": uid,
            "resource_id": None if res == "money" else ids[res],
            "resource": res,
            "required_amount": math.ceil(amount / TICKS_PER_YEAR),
        }
        for (uid, res), amount in totals.items()
    ]
