"""Wear-out (ledger_wearout flag): industrial buildings wear out and need Machinery to keep running at full output.

Every hour, a nation's fleet of extraction + processing buildings needs ceil(fleet / BUILDINGS_PER_MACHINERY) Machinery.
The tick consumes what it can; output of those buildings is scaled by FLOOR + (1 - FLOOR) * cover, where cover = stock / need
(clamped 0..1). The floor means a nation without Machinery runs at 50%, never at zero, so there is no death spiral.
Demand ramps up over RAMP_HOURS after the flag is enabled (counted in revenue ticks, one per hour), so there is no shock on activation.
Called once per revenue tick before the province loop. Flag off -> returns {} and touches nothing."""
import logging, math
import variables
from app_core.feature_flags import is_on

logger = logging.getLogger(__name__)
BUILDINGS_PER_MACHINERY = 50
FLOOR = 0.5
RAMP_HOURS = 336      # demand ramps from 10% to 100% over 14 days after the flag is switched on
RAMP_START = 0.10
CATEGORIES = ("industry", "processing")


FOOD_EXEMPT = ("farms", "fisheries")  # rations are protected: food buildings never wear out


def worn_buildings():
    out = []
    for c in CATEGORIES:
        out += [b for b in variables.INFRA_TYPE_BUILDINGS.get(c, []) if b not in FOOD_EXEMPT]
    return out


def apply(cur, user_ids, resources_map, resource_deltas):
    """Returns {user_id: output_factor}; adds Machinery consumption to resource_deltas."""
    users = [u for u in user_ids if is_on("ledger_wearout", u)] if is_on("ledger_goods") else []
    if not users:
        return {}
    cur.execute("INSERT INTO ledger_wear_meta (id, ticks) VALUES (1, 1) ON CONFLICT (id) DO UPDATE SET ticks = ledger_wear_meta.ticks + 1 RETURNING ticks")
    row = cur.fetchone()
    hours_on = float((row["ticks"] if isinstance(row, dict) else row[0]) or 0)
    ramp = min(1.0, RAMP_START + (1 - RAMP_START) * hours_on / RAMP_HOURS)
    cur.execute(
        """SELECT ub.user_id, COALESCE(SUM(ub.quantity), 0) AS fleet
           FROM user_buildings ub JOIN building_dictionary bd ON bd.building_id = ub.building_id
           WHERE ub.user_id = ANY(%s) AND bd.name = ANY(%s) GROUP BY ub.user_id""",
        (users, worn_buildings()),
    )
    fleets = {}
    for r in cur.fetchall():
        uid = r["user_id"] if isinstance(r, dict) else r[0]
        fleets[uid] = int(r["fleet"] if isinstance(r, dict) else r[1])
    factors, rows = {}, []
    for uid in users:
        fleet = fleets.get(uid, 0)
        need = math.ceil(fleet / BUILDINGS_PER_MACHINERY * ramp) if fleet else 0
        stock = int((resources_map.get(uid) or {}).get("machinery", 0))
        cover = 1.0 if need == 0 else min(1.0, stock / need)
        factors[uid] = FLOOR + (1 - FLOOR) * cover
        used = min(stock, need)
        if used:
            resource_deltas.setdefault(uid, {})["machinery"] = resource_deltas.get(uid, {}).get("machinery", 0) - used
        rows.append((uid, fleet, need, stock, round(cover, 4)))
    cur.executemany(
        """INSERT INTO ledger_wear_state (user_id, fleet, need, stock, cover, updated_at) VALUES (%s,%s,%s,%s,%s,now())
           ON CONFLICT (user_id) DO UPDATE SET fleet=EXCLUDED.fleet, need=EXCLUDED.need, stock=EXCLUDED.stock, cover=EXCLUDED.cover, updated_at=now()""",
        rows,
    )
    return factors
