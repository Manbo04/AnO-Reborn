"""One decision round on the SIM server: dump state -> agy decides per nation -> execute via HTTP. Mac-side orchestrator.
Usage: python3 sim_round.py <nations> <seed> <batch>"""
import sys, json, subprocess, re, time
N, SEED, B, CT = int(sys.argv[1]), sys.argv[2], int(sys.argv[3]), sys.argv[4]
SSH = ["ssh", "Dede@100.75.49.7"]
def sh(cmd, inp=None, t=600):
    return subprocess.run(SSH + [cmd], input=inp, capture_output=True, text=True, timeout=t).stdout
raw = sh(f"docker exec {CT} python testrealm/sim_state.py {N} {SEED} 2>/dev/null | tail -1")
states = json.loads(raw)
for s in states:
    s["buildings"] = {k: v for k, v in s["buildings"].items() if v}
RULES = """You are a player-decision engine for a nation-simulation game (Affairs and Order). For EACH nation below choose up to 4 actions this round, as a smart human player would, spending gold sensibly (keep ~10% reserve), fixing shortages first (energy, rations), then growing industry, then military/expansion.
NEW RULE THIS WORLD: industrial buildings wear out and need Machinery (see each nation's "wear": need_per_h, machinery stock, output_pct). Without Machinery, mines/mills/refineries/factories run at only 50% output. Machinery comes from machinery_works (steel 30 + components 12 -> 24 machinery/h, city slot building) or can be bought on the market. Keep output_pct near 100.
Allowed ops (JSON): {"op":"build","building":NAME,"province":ID,"qty":N} | {"op":"buy_land","province":ID,"qty":N} | {"op":"buy_city","province":ID,"qty":N} | {"op":"military","unit":NAME,"qty":N} | {"op":"sell","resource":NAME,"amount":N,"price":N} | {"op":"buy","offer_id":ID,"amount":N}  (buy from the nation's "market" list = cheapest sell offers per resource; cost = amount*price gold; use it to get Machinery or inputs you lack)
Building names: coal_mines iron_mines bauxite_mines copper_mines lead_mines uranium_mines pumpjacks farms lumber_mills steel_mills aluminium_refineries oil_refineries component_factories ammunition_factories machinery_works coal_burners oil_burners solar_fields hydro_dams nuclear_reactors hospitals city_parks malls general_stores banks.
Only build city/land buildings where province has free slots (land_free/city_free). Mines, farms, lumber, pumpjacks use land; factories, refineries, power, malls use city slots roughly. Prefer cheap sensible moves.
Reply with ONLY a JSON list: [{"uid":ID,"name":"NAME","actions":[...]}, ...] for every nation given, no prose."""
decisions = []
t0 = time.time()
from concurrent.futures import ThreadPoolExecutor
def ask(batch):
    prompt = RULES + "\n\nNATIONS:\n" + json.dumps(batch)
    for attempt in (1, 2):
        try:
            out = subprocess.run(["agy", "-p", prompt, "--model", "gemini-3.8-flash-high", "--dangerously-skip-permissions", "--output-format", "text"], capture_output=True, text=True, timeout=420).stdout
            m = re.search(r"\[.*\]", out, re.S)
            return json.loads(m.group(0))
        except Exception as e:
            print("batch attempt", attempt, "failed:", type(e).__name__, flush=True)
    return []
with ThreadPoolExecutor(5) as ex:
    for part in ex.map(ask, [states[i:i + B] for i in range(0, len(states), B)]): decisions += part
print("batches ok/total:", sum(1 for _ in decisions), "nations decided of", len(states), flush=True)
print("agy decided", len(decisions), "nations in", round(time.time() - t0), "s")
for d in decisions:
    for a in d.get("actions", []): pass
res = sh("SIM_PW=$(cat ~/ano-realm/.realm_pw); docker exec -i -e SIM_PW=$SIM_PW " + CT + " python testrealm/sim_act.py 2>/dev/null | tail -1", inp=json.dumps(decisions))
r = json.loads(res)
from collections import Counter
print(Counter((x.get("op"), str(x.get("code"))) for x in r))
json.dump({"decisions": decisions, "results": r}, open(f"round_{CT}.json", "w"))
