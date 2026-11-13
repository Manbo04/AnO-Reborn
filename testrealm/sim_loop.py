"""Flags off vs on, agy decides for every sampled nation each round, ticks run between rounds. Mac-side. SIM DBs only.
Usage: python3 sim_loop.py <rounds> <ticks_per_round> <nations>"""
import sys, subprocess, json, csv, time
R, T, N = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
SSH = ["ssh", "Dede@100.75.49.7"]
def sh(c, t=3000): return subprocess.run(SSH + [c], capture_output=True, text=True, timeout=t).stdout
Q = """SELECT 'gold_B', round(sum(gold)/1e9) FROM stats UNION ALL
SELECT 'steel_M', round(sum(quantity)/1e6) FROM user_economy ue JOIN resource_dictionary rd USING(resource_id) WHERE rd.name='steel' UNION ALL
SELECT 'machinery', coalesce(sum(quantity),0) FROM user_economy ue JOIN resource_dictionary rd USING(resource_id) WHERE rd.name='machinery' UNION ALL
SELECT 'works', coalesce(sum(ub.quantity),0) FROM user_buildings ub JOIN building_dictionary bd USING(building_id) WHERE bd.name='machinery_works' UNION ALL
SELECT 'works_owners', count(distinct ub.user_id) FROM user_buildings ub JOIN building_dictionary bd USING(building_id) WHERE bd.name='machinery_works' AND ub.quantity>0 UNION ALL
SELECT 'avg_output_pct', coalesce(round(avg(50+50*cover)),100) FROM ledger_wear_state WHERE need>0 UNION ALL
SELECT 'fleet_nations', count(*) FROM ledger_wear_state WHERE need>0 UNION ALL
SELECT 'nations_below_90pct', count(*) FROM ledger_wear_state WHERE need>0 AND cover<0.8"""
def metrics(w):
    out = sh(f"docker exec -i anotest-postgres-1 psql -U ano_test -d ano_sim_{w} -At -F' ' -c \"{Q}\"")
    return dict(l.split(" ", 1) for l in out.strip().splitlines() if " " in l)
KEYS = ["gold_B", "steel_M", "machinery", "works", "works_owners", "avg_output_pct", "fleet_nations", "nations_below_90pct"]
w = csv.writer(open("sim_loop.csv", "w")); w.writerow(["round", "world"] + KEYS + ["ok_actions", "failed_actions"])
for rnd in range(1, R + 1):
    for world in ("off", "on"):
        t0 = time.time()
        import os
        try: os.remove(f"round_anosim-{world}.json")
        except FileNotFoundError: pass
        o = subprocess.run(["python3", "sim_round.py", N, "7", "10", f"anosim-{world}"], capture_output=True, text=True, timeout=3000)
        print("   round log:", " | ".join(x for x in (o.stdout + o.stderr).splitlines() if "decided" in x or "failed" in x or "ok/total" in x)[:300], flush=True)
        sh(f"docker exec anosim-{world} python testrealm/sim_ticks.py {T} 2>&1 | tail -1")
        try: res = json.load(open(f"round_anosim-{world}.json"))["results"]
        except Exception: res = []; print("ROUND FAILED", rnd, world, (o.stdout + o.stderr)[-300:], flush=True)
        ok = sum(1 for x in res if str(x.get("code")) in ("302", "200")); bad = len(res) - ok
        m = metrics(world)
        w.writerow([rnd, world] + [m.get(k, "") for k in KEYS] + [ok, bad])
        print(rnd, world, m, "ok", ok, "bad", bad, round(time.time() - t0), "s", flush=True)
