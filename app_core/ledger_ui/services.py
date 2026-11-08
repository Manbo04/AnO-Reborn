"""Read-only data for the Ledger page. Nothing here writes to the database."""
import math

import variables

# Buildings that turn inputs into goods (recipes come from variables.NEW_INFRA).
CHAINS = [
    "oil_refineries", "steel_mills", "aluminium_refineries",
    "component_factories", "ammunition_factories",
]
LABELS = {
    "oil_refineries": "Oil Refineries", "steel_mills": "Steel Mills",
    "aluminium_refineries": "Aluminium Refineries",
    "component_factories": "Component Factories",
    "ammunition_factories": "Ammunition Factories",
}


def _stock(db, uid):
    db.execute("SELECT * FROM resources WHERE id=%s", (uid,))
    row = db.fetchone()
    if not row:
        return {}
    cols = [d[0] for d in db.description]
    return {c: (v or 0) for c, v in zip(cols, row)}


def industry(db, uid):
    sel = ", ".join("COALESCE(SUM(i.%s),0)" % b for b in CHAINS)
    db.execute(
        "SELECT %s FROM provinces p JOIN proinfra i ON i.id=p.id WHERE p.userid=%%s" % sel,
        (uid,),
    )
    counts = dict(zip(CHAINS, [int(x) for x in db.fetchone()]))
    stock = _stock(db, uid)
    rows = []
    for b in CHAINS:
        n = counts[b]
        spec = variables.NEW_INFRA.get(b, {})
        minus, plus = spec.get("minus", {}), spec.get("plus", {})
        if n <= 0:
            continue
        inputs, can_run, limiter = [], n, None
        for res, per in minus.items():
            have = stock.get(res, 0)
            afford = int(have // per) if per else n
            need_hr = n * per
            inputs.append({
                "res": res, "per": per, "need_hr": need_hr, "have": have,
                "hours": (have / need_hr) if need_hr else None,
                "afford": afford,
            })
            if afford < can_run:
                can_run, limiter = afford, res
        can_run = max(0, min(n, can_run))
        out_res, out_per = next(iter(plus.items()), ("", 0))
        rows.append({
            "key": b, "label": LABELS[b], "count": n, "running": can_run,
            "pct": round(100 * can_run / n) if n else 0, "limiter": limiter,
            "inputs": inputs, "out_res": out_res,
            "out_hr": out_per * can_run, "out_full": out_per * n,
            "upkeep": int(spec.get("money", 0) * can_run),
        })
    return rows


def needs(db, uid):
    db.execute("SELECT COALESCE(SUM(population),0) FROM provinces WHERE userid=%s", (uid,))
    pop = int(db.fetchone()[0])
    stock = _stock(db, uid)
    r_need = max(int(pop // variables.RATIONS_PER), 1)
    cg_need = max(int(pop // variables.CONSUMER_GOODS_PER), 1)
    tiers = [
        {"tier": 1, "name": "Subsistence", "res": "rations", "need_hr": r_need,
         "have": stock.get("rations", 0), "live": True},
        {"tier": 2, "name": "Comfort", "res": "consumer_goods", "need_hr": cg_need,
         "have": stock.get("consumer_goods", 0), "live": True},
    ]
    for t in tiers:
        t["hours"] = t["have"] / t["need_hr"] if t["need_hr"] else None
        t["pct"] = min(100, round(100 * t["hours"] / 24)) if t["hours"] is not None else 0
    return {"people": pop, "tiers": tiers}


def budget(db, uid):
    out = {"old": None, "new": None, "delta": None, "rank": None, "of": None}
    db.execute("SELECT old_income, new_income FROM ledger_income_shadow WHERE user_id=%s", (uid,))
    r = db.fetchone()
    if r:
        old, new = int(r[0] or 0), int(r[1] or 0)
        out.update(old=old, new=new, delta=(round(100 * (new - old) / old, 1) if old else None))
        db.execute("SELECT COUNT(*) FILTER (WHERE new_income > %s), COUNT(*) FROM ledger_income_shadow", (new,))
        a, b = db.fetchone()
        out.update(rank=int(a) + 1, of=int(b))
    try:
        db.execute("SELECT gold FROM stats WHERE id=%s", (uid,))
        g = db.fetchone()
        out["gold"] = int(g[0]) if g else None
    except Exception:
        db.connection.rollback()
        out["gold"] = None
    return out


def gazette(db):
    db.execute(
        "SELECT ts, humans, gold_total, gold_median, top10pct_share FROM ledger_snapshots "
        "ORDER BY ts DESC LIMIT 14"
    )
    rows = [{"ts": r[0], "humans": r[1], "total": int(r[2]), "median": int(r[3]),
             "top10": float(r[4])} for r in db.fetchall()][::-1]
    latest = rows[-1] if rows else None
    first = rows[0] if rows else None
    db.execute("SELECT COALESCE(SUM(population),0) FROM provinces")
    pop = int(db.fetchone()[0])
    db.execute("SELECT resources FROM ledger_snapshots ORDER BY ts DESC LIMIT 1")
    r = db.fetchone()
    res = (r[0] or {}) if r else {}
    cover = []
    need_map = {"rations": max(pop // variables.RATIONS_PER, 1),
                "consumer_goods": max(pop // variables.CONSUMER_GOODS_PER, 1)}
    for k, need in need_map.items():
        have = float(res.get(k, 0) or 0)
        cover.append({"res": k, "have": have, "need_hr": need, "days": have / need / 24.0})
    try:
        db.execute("SELECT MAX(s.gold)::float / NULLIF(SUM(s.gold),0) FROM stats s JOIN users u ON u.id=s.id WHERE u.auth_type<>'bot' AND s.gold>0")
        top1 = float(db.fetchone()[0] or 0)
    except Exception:
        db.connection.rollback()
        top1 = 0.0
    return {"rows": rows, "latest": latest, "first": first, "cover": cover, "pop": pop, "top1": top1}
