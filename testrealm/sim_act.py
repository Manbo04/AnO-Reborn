"""Execute decisions {uid:[{op,...}]} via real HTTP routes on the SIM server. stdin JSON list of {uid,name,actions:[...]}. Prints results JSON."""
import os, sys, json
assert "sim" in os.environ.get("PG_DATABASE", ""), "refusing: PG_DATABASE must contain 'sim'"
import simclient
simclient.BASE = "http://127.0.0.1:8080"
from database import get_db_connection
PW = os.environ["SIM_PW"]
with get_db_connection() as c:
    cur = c.cursor(); cur.execute("SELECT building_id, name FROM building_dictionary WHERE is_active=TRUE")
    BID = {(r["name"] if isinstance(r, dict) else r[1]): (r["building_id"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
res = []
for d in json.load(sys.stdin):
    n = simclient.Nation(d["name"], PW)
    if not n.ok:
        res.append({"uid": d["uid"], "err": "login"}); continue
    for a in d["actions"][:6]:
        op = a.get("op"); code = None
        try:
            if op == "build" and a.get("building") in BID:
                r = n.post("/build_structure", {"building_id": str(BID[a["building"]]), "quantity": str(min(int(a.get("qty", 1)), 20)), "province_id": str(a["province"])})
            elif op == "buy_land": r = n.post(f"/buy/land/{a['province']}", {"land": str(min(int(a.get("qty", 1)), 5))})
            elif op == "buy_city": r = n.post(f"/buy/cityCount/{a['province']}", {"cityCount": str(min(int(a.get("qty", 1)), 5))})
            elif op == "military": r = n.post(f"/military/buy/{a['unit']}", {a["unit"]: str(min(int(a.get("qty", 1)), 50))})
            elif op == "sell": r = n.post("/post_offer/sell", {"resource": a["resource"], "amount": str(int(a["amount"])), "price": str(int(a["price"]))})
            else: r = None
            code = r.status_code if r is not None else "skip"
        except Exception as e:
            code = "err:" + repr(e)[:60]
        res.append({"uid": d["uid"], "op": op, "code": code})
print(json.dumps(res))
