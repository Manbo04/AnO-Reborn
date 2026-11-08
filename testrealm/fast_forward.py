"""Fast-forward the realm economy: run the hourly ticks back to back on a CLONE database (never prod, never the live realm DB).
Usage (inside the web image, PG_DATABASE=ano_sim): python testrealm/fast_forward.py <hours> [csv_out]
Humans do nothing in this sim: it measures passive drift of the economy (tax, upkeep, population, manpower, loans)."""
import sys,os,time,csv
assert "sim" in os.environ.get("PG_DATABASE",""), "refusing: PG_DATABASE must contain 'sim'"
import tasks
from database import get_db_connection
H=int(sys.argv[1]); out=sys.argv[2] if len(sys.argv)>2 else "/tmp/ff.csv"
def reset_claims():
    with get_db_connection() as c:
        cur=c.cursor(); cur.execute("UPDATE task_runs SET last_run=NULL, last_period=NULL"); c.commit()
def snap(day,hour):
    with get_db_connection() as c:
        cur=c.cursor()
        cur.execute("""SELECT count(*), coalesce(sum(s.gold),0), coalesce(percentile_cont(0.5) WITHIN GROUP (ORDER BY s.gold),0),
          (SELECT coalesce(sum(g),0) FROM (SELECT s2.gold g, ntile(10) OVER (ORDER BY s2.gold DESC) t FROM stats s2 JOIN users u2 ON u2.id=s2.id WHERE u2.auth_type<>'bot') x WHERE t=1),
          (SELECT coalesce(sum(population),0) FROM provinces p JOIN users u3 ON u3.id=p.userid WHERE u3.auth_type<>'bot'),
          (SELECT count(*) FROM stats s4 JOIN users u4 ON u4.id=s4.id WHERE u4.auth_type<>'bot' AND s4.gold<=0)
          FROM stats s JOIN users u ON u.id=s.id WHERE u.auth_type<>'bot'""")
        n,tot,med,top,pop,broke=cur.fetchone()
        return [day,hour,n,int(tot),int(med),round(float(top)/float(tot),4) if tot else 0,int(pop),broke]
w=csv.writer(open(out,"w")); w.writerow(["day","hour","humans","gold_total","gold_median","top10_share","human_pop","humans_gold_le0"])
w.writerow(snap(0,0)); t0=time.time()
steps=[tasks.task_tax_income,tasks.task_generate_province_revenue,tasks.task_produce_unit_stockpiles,tasks.task_population_growth,tasks.task_loan_interest]
for h in range(1,H+1):
    reset_claims()
    for f in steps+([tasks.task_manpower_increase] if h%4==0 else [])+([tasks.task_war_reparation_tax] if h%24==0 else []):
        try: f()
        except Exception as e: print("tick error",h,f.__name__,repr(e)[:120],flush=True)
    if h%24==0:
        w.writerow(snap(h//24,0)); open(out,"a").flush(); print("day",h//24,"done",round(time.time()-t0),"s",flush=True)
print("finished",H,"hours in",round(time.time()-t0),"s")
