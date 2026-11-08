"""Dump compact state of sampled human nations from the SIM db as JSON. Usage: python sim_state.py <n> <seed>"""
import os, sys, json, random
assert "sim" in os.environ.get("PG_DATABASE", ""), "refusing: PG_DATABASE must contain 'sim'"
from database import get_db_connection
from ai_agent import GameState
N = int(sys.argv[1]); random.seed(int(sys.argv[2]))
with get_db_connection() as c:
    cur = c.cursor(); cur.execute("SELECT id, username FROM users WHERE auth_type<>'bot' ORDER BY id"); rows = cur.fetchall()
rows = [(r[0], r[1]) if not isinstance(r, dict) else (r["id"], r["username"]) for r in rows]
pick = random.sample(rows, min(N, len(rows)))
out = []
for uid, name in pick:
    st = GameState(uid); st.load()
    stock = {k: v for k, v in st.resources.items() if v}
    out.append({"uid": uid, "name": name, "gold": int(st.gold), "pop": int(st.population), "happy": round(st.happiness or 0),
        "res": stock, "buildings": st.total_buildings,
        "provs": [{"id": p["id"], "land_free": st.get_free_land_slots(p), "city_free": st.get_free_city_slots(p)} for p in st.provinces][:6],
        "n_prov": st.province_count})
print(json.dumps(out))
