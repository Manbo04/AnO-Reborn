"""Dump compact state of sampled human nations from the SIM db as JSON. Usage: python sim_state.py <n> <seed>"""
import os, sys, json, random
assert "sim" in os.environ.get("PG_DATABASE", ""), "refusing: PG_DATABASE must contain 'sim'"
from database import get_db_connection
from ai_agent import GameState
N = int(sys.argv[1]); random.seed(int(sys.argv[2]))
with get_db_connection() as c:
    cur = c.cursor(); cur.execute("SELECT id, username FROM users WHERE auth_type<>'bot' ORDER BY id"); rows = cur.fetchall()
rows = [(r[0], r[1]) if not isinstance(r, dict) else (r["id"], r["username"]) for r in rows]
with get_db_connection() as c:
    cur = c.cursor()
    cur.execute("""SELECT DISTINCT ub.user_id FROM user_buildings ub JOIN building_dictionary bd USING(building_id)
        WHERE ub.quantity>0 AND bd.name IN ('farms','pumpjacks','coal_mines','bauxite_mines','copper_mines','uranium_mines','lead_mines','iron_mines','lumber_mills','silver_mines','diamond_mines','bullion_mines','fisheries','component_factories','steel_mills','ammunition_factories','machinery_works','aluminium_refineries','oil_refineries')""")
    ind = {(r["user_id"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
first = [r for r in rows if r[0] in ind]; rest = [r for r in rows if r[0] not in ind]
random.shuffle(first); random.shuffle(rest)
pick = (first + rest)[:N]
with get_db_connection() as c:
    cur = c.cursor()
    try:
        cur.execute("SELECT user_id, fleet, need, stock, cover FROM ledger_wear_state")
        wear = {(r["user_id"] if isinstance(r, dict) else r[0]): {"need_per_h": (r["need"] if isinstance(r, dict) else r[2]), "machinery": (r["stock"] if isinstance(r, dict) else r[3]), "output_pct": round(50 + 50 * float(r["cover"] if isinstance(r, dict) else r[4]))} for r in cur.fetchall()}
    except Exception:
        wear = {}
with get_db_connection() as c:
    cur = c.cursor()
    cur.execute("""SELECT offer_id, resource, amount, price, user_id FROM (
        SELECT o.*, row_number() OVER (PARTITION BY resource ORDER BY price, offer_id) rn FROM offers o
        WHERE type='sell' AND resource IN ('machinery','steel','components','iron','copper','aluminium','coal','lead','bauxite') AND amount>0) x WHERE rn<=2""")
    market = {}
    for r in cur.fetchall():
        r = r if isinstance(r, dict) else dict(zip(["offer_id","resource","amount","price","user_id"], r))
        market.setdefault(r["resource"], []).append({"offer_id": r["offer_id"], "amount": int(r["amount"]), "price": int(r["price"]), "seller": r["user_id"]})
out = []
for uid, name in pick:
    st = GameState(uid); st.load()
    stock = {k: v for k, v in st.resources.items() if v}
    out.append({"uid": uid, "name": name, "gold": int(st.gold), "pop": int(st.population), "happy": round(st.happiness or 0),
        "res": stock, "buildings": st.total_buildings,
        "provs": [{"id": p["id"], "land_free": st.get_free_land_slots(p), "city_free": st.get_free_city_slots(p)} for p in st.provinces][:6],
        "n_prov": st.province_count, "wear": wear.get(uid), "market": {k: [o for o in v if o["seller"] != uid] for k, v in market.items()}})
print(json.dumps(out))
