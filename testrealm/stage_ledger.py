"""Ledger Lite staging on the test realm (runs on vivobook). Test account 16 only."""
import os,re,sys,subprocess,urllib.request,urllib.parse,http.cookiejar
B="http://127.0.0.1:18080"
PW=open(os.path.expanduser("~/ano-realm/.realm_pw")).read().strip()
cj=http.cookiejar.CookieJar()
class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k): return None
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),NR)
def get(u):
    try: r=op.open(B+u); return r.status,r.read().decode(),r.headers
    except urllib.error.HTTPError as e: return e.code,e.read().decode(),e.headers
def tok(u):
    _,h,_=get(u); m=re.search(r'name="csrf_token"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*name="csrf_token"|csrf-token" content="([^"]+)"',h); return next(x for x in m.groups() if x)
def post(u,d,page="/provinces"):
    for _ in range(4):
        d=dict(d); d["csrf_token"]=tok(page)
        rq=urllib.request.Request(B+u,urllib.parse.urlencode(d).encode(),{"Origin":B})
        try: r=op.open(rq); c,h,hd=r.status,r.read().decode(),r.headers
        except urllib.error.HTTPError as e: c,h,hd=e.code,e.read().decode(),e.headers
        if "form expired" not in h: return c,h,hd
    return c,h,hd
def sql(q): return subprocess.run(["docker","exec","anotest-postgres-1","psql","-U","ano_test","-d","ano_test","-Atc",q],capture_output=True,text=True).stdout.strip()
def flags(on):
    for k in ("ledger_low_fee","ledger_sellback_haircut","ledger_bank_blockade"):
        sql(f"INSERT INTO feature_flags(key,enabled,rollout_percent,description,rollback_trigger,updated_by) VALUES('{k}',{'true' if on else 'false'},100,'Ledger Lite experiment (realm only)','set enabled=false','stage') ON CONFLICT(key) DO UPDATE SET enabled={'true' if on else 'false'}")
    import time; time.sleep(17)  # flag cache is 15s
print("login",post("/login",{"username":"Tester of the Game","password":PW},"/login")[0])
gold=lambda:int(sql("select gold from stats where id=16"))
def roundtrip(n=1000):
    sql("UPDATE stats SET gold=10000000000000, manpower=1000000000 WHERE id=16")
    sql("UPDATE user_economy SET quantity=quantity+10000000000 WHERE user_id=16")
    g0=gold(); c1=post("/military/buy/soldiers",{"soldiers":str(n)})[0]; g1=gold()
    c2=post("/military/sell/soldiers",{"soldiers":str(n)})[0]; g2=gold()
    spent=g0-g1; back=g2-g1
    return c1,c2,spent,back,(back/spent if spent else None)
# bank freeze
import json
cm=sql("select table_name from information_schema.tables where table_name in ('coalition_members','coalitions_legacy')")
print("tables",cm.split())
sql("DELETE FROM coalitions_legacy WHERE userid=16")
print("member insert:",sql("INSERT INTO coalitions_legacy(colid,userid,role) VALUES (2,16,'member') RETURNING userid"))
print("reopen staged war",sql("UPDATE wars SET status='active',peace_date=NULL WHERE id=638 AND attacker=16 RETURNING id"))
sql("UPDATE wars SET attacker_blockaded=now()+interval '1 hour' WHERE attacker=16 AND peace_date IS NULL")
for state in (False,True):
    flags(state)
    g0=gold(); c,h2,hd=post("/deposit_into_bank/2",{"deposit_destination":"personal","money":"1"},"/coalition/2")
    t=re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",h2))[:140]
    print(" bank deposit under blockade, flags","ON" if state else "OFF","code",c,"|",t, "| location",hd.get("Location"))
    print("   gold moved into bank (1 expected if NOT frozen, 0 if frozen):", g0-gold())
print("cleanup war",sql("UPDATE wars SET peace_date=extract(epoch from now()),status='ended',attacker_blockaded=NULL WHERE attacker=16 AND peace_date IS NULL RETURNING id"))
sql("DELETE FROM coalitions_legacy WHERE userid=16")
flags(False)
