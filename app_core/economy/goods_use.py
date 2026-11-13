"""Goods use (flag ledger_goods_use): the new atlas goods get consumed.

Per nation, per hourly tick (demand ramps 10% -> 100% over RAMP_HOURS after activation, counted in revenue ticks):
- Clothing: population need, 1 per CLOTHING_POP people/h.  Shortfall -> up to -CLOTHING_PEN happiness in every province.
- Medicine: hospitals use MED_PER_HOSPITAL/h each.        Shortfall -> up to -MED_PEN happiness (only if the nation has hospitals).
- Fertilizer: farms use FERT_PER_FARM/h each, optional.   Covered -> farm output x(1 + FERT_BONUS * cover). No penalty without it.
- Prosperity (electronics, vehicles, luxury goods): 1 each per PROSP_POP people/h. Average cover -> up to +PROSP_BONUS happiness.
Plastics and chemicals are inputs only (electronics / medicine / fertilizer chains). Flag off -> returns empty dicts, touches nothing.
Returns {"farm": {uid: factor}, "happy": {uid: delta}}.""" 
import logging, math
from app_core.feature_flags import is_on

logger = logging.getLogger(__name__)
RAMP_HOURS, RAMP_START = 336, 0.10
CLOTHING_POP, MED_PER_HOSPITAL, FERT_PER_FARM, PROSP_POP = 200_000, 2, 1, 1_000_000
CLOTHING_PEN, MED_PEN, FERT_BONUS, PROSP_BONUS = 5.0, 4.0, 0.20, 5.0
PROSPERITY = ("electronics", "vehicles", "luxury_goods")


def _cover(stock, need):
    return 1.0 if need <= 0 else min(1.0, stock / need)


def apply(cur, user_ids, resources_map, resource_deltas):
    users = [u for u in user_ids if is_on("ledger_goods_use", u)]
    if not users:
        return {"farm": {}, "happy": {}}
    cur.execute("INSERT INTO ledger_goods_meta (id, ticks) VALUES (1, 1) ON CONFLICT (id) DO UPDATE SET ticks = ledger_goods_meta.ticks + 1 RETURNING ticks")
    row = cur.fetchone()
    hours_on = float((row["ticks"] if isinstance(row, dict) else row[0]) or 0)
    ramp = min(1.0, RAMP_START + (1 - RAMP_START) * hours_on / RAMP_HOURS)
    def rows(sql, args):
        cur.execute(sql, args)
        return [(r["a"], r["b"]) if isinstance(r, dict) else (r[0], r[1]) for r in cur.fetchall()]
    pops = dict(rows("SELECT userid AS a, COALESCE(SUM(population),0) AS b FROM provinces WHERE userid = ANY(%s) GROUP BY userid", (users,)))
    def count(b):
        return dict(rows("""SELECT ub.user_id AS a, COALESCE(SUM(ub.quantity),0) AS b FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id WHERE ub.user_id = ANY(%s) AND bd.name = %s GROUP BY ub.user_id""", (users, b)))
    farms, hospitals = count("farms"), count("hospitals")
    farm_f, happy, state = {}, {}, []
    for uid in users:
        have = resources_map.get(uid) or {}
        d = resource_deltas.setdefault(uid, {})
        pop = int(pops.get(uid, 0) or 0)
        def use(name, need):
            stock = int(have.get(name, 0)) + d.get(name, 0)
            used = min(max(stock, 0), need)
            if used: d[name] = d.get(name, 0) - used
            return _cover(max(stock, 0), need)
        c_cl = use("clothing", math.ceil(pop / CLOTHING_POP * ramp))
        nh = int(hospitals.get(uid, 0) or 0)
        c_md = use("medicine", math.ceil(nh * MED_PER_HOSPITAL * ramp)) if nh else 1.0
        nf = int(farms.get(uid, 0) or 0)
        c_fe = use("fertilizer", math.ceil(nf * FERT_PER_FARM * ramp)) if nf else 0.0
        c_pr = sum(use(g, math.ceil(pop / PROSP_POP * ramp)) for g in PROSPERITY) / len(PROSPERITY)
        farm_f[uid] = 1.0 + FERT_BONUS * c_fe
        happy[uid] = ramp * (-CLOTHING_PEN * (1 - c_cl) - (MED_PEN * (1 - c_md) if nh else 0)) + PROSP_BONUS * c_pr * ramp
        state.append((uid, round(c_cl, 4), round(c_md, 4), round(c_fe, 4), round(c_pr, 4), round(happy[uid], 3)))
    cur.executemany("""INSERT INTO ledger_goods_state (user_id, clothing, medicine, fertilizer, prosperity, happy, updated_at) VALUES (%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (user_id) DO UPDATE SET clothing=EXCLUDED.clothing, medicine=EXCLUDED.medicine, fertilizer=EXCLUDED.fertilizer, prosperity=EXCLUDED.prosperity, happy=EXCLUDED.happy, updated_at=now()""", state)
    return {"farm": farm_f, "happy": happy}
