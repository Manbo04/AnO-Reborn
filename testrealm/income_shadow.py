"""Ledger income-rebase SHADOW (v2). Read-only on game tables; writes only ledger_income_shadow. Run on the vivobook.
v2: keep today's tax formula (food, consumer goods, demographics all stay) and scale each nation by a rank multiplier
m = (0.75+0.25*U)*(0.75+0.25*I), U/I = percentile ranks of cities-per-land and non-military-buildings-per-worker
among human nations. Divided by the MEDIAN m so the median nation is unchanged.
v3: times an overextension factor min(1, 40/provinces)^0.75, because one nation with 500 provinces earns ~44% of all human income.
(v1 replaced the formula and calibrated on the total, which one nation dominates.)"""
import subprocess, statistics as st
def q(sql):
    r = subprocess.run(["docker","exec","anotest-postgres-1","psql","-U","ano_test","-d","ano_test","-AtF","|","-c",sql], capture_output=True, text=True)
    if r.returncode: raise SystemExit(r.stderr)
    return [l.split("|") for l in r.stdout.strip().split("\n") if l]
rows = q("""
WITH t AS (SELECT DISTINCT ON (user_id) user_id, amount FROM nation_revenue_history WHERE category='tax' ORDER BY user_id, recorded_at DESC),
p AS (SELECT userid, sum(population) pop, sum(pop_working) wk, sum(citycount) cities, sum(land) land FROM provinces GROUP BY userid),
b AS (SELECT ub.user_id, sum(ub.quantity) n FROM user_buildings ub JOIN building_dictionary bd USING (building_id) WHERE bd.category<>'military' GROUP BY 1)
SELECT u.id, t.amount, p.pop, p.wk, p.cities, p.land, coalesce(b.n,0) FROM users u JOIN t ON t.user_id=u.id JOIN p ON p.userid=u.id LEFT JOIN b ON b.user_id=u.id
WHERE u.auth_type<>'bot' AND p.pop>0 AND t.amount>0""")
pc = {int(r[0]): int(r[1]) for r in q("SELECT userid, count(*) FROM provinces GROUP BY userid")}
d = [dict(id=int(r[0]), old=int(r[1]), pop=int(r[2]), wk=max(1,int(r[3])), urb=int(r[4])/max(1,int(r[5])), ind=int(r[6])/max(1,int(r[3])), n=pc.get(int(r[0]),1)) for r in rows]
def rank(key):
    s = sorted(x[key] for x in d); n = len(s)-1 or 1
    for x in d: x[key+"_r"] = s.index(x[key])/n
rank("urb"); rank("ind")
m = [(0.75+0.25*x["urb_r"])*(0.75+0.25*x["ind_r"]) for x in d]
K = st.median(m)
for x, r in zip(d, m):
    over = min(1.0, 40.0/x["n"])**0.75   # overextension: provinces beyond 40 earn less each
    x["new"] = x["old"]*r/K*over; x["ratio"] = r/K*over
def gini(v):
    v = sorted(v); n = len(v); c = sum((i+1)*a for i,a in enumerate(v)); return 2*c/(n*sum(v))-(n+1)/n
def top10(v):
    v = sorted(v, reverse=True); return sum(v[:max(1, len(v)//10)])/sum(v)
o = [x["old"] for x in d]; n = [x["new"] for x in d]
print("nations compared:", len(d), " median multiplier %.3f" % K)
print("total old %d  new %d" % (sum(o), sum(n)))
print("old: median %d gini %.3f top10 %.3f" % (st.median(o), gini(o), top10(o)))
print("new: median %d gini %.3f top10 %.3f" % (st.median(n), gini(n), top10(n)))
rt = sorted(x["ratio"] for x in d)
print("new/old p5/p25/p50/p75/p95:", [round(rt[int(len(rt)*p)], 2) for p in (.05,.25,.5,.75,.95)])
q("CREATE TABLE IF NOT EXISTS ledger_income_shadow(ts timestamptz DEFAULT now(), user_id int, old_income bigint, new_income bigint)")
q("DELETE FROM ledger_income_shadow")
vals = ",".join("(%d,%d,%d)" % (x["id"], x["old"], int(x["new"])) for x in d)
q("INSERT INTO ledger_income_shadow(user_id,old_income,new_income) VALUES " + vals)
