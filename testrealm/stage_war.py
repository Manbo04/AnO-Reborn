"""Stage a war on the test realm and check the war-sell block both ways.

Runs on the realm host. Env: TESTREALM_PW_FILE (shared tester password file, default ~/ano-realm/.realm_pw),
SKIP_AI (comma-separated AI nation ids to skip, e.g. ones under a truce). Uses the test account only.
If declaring fails with 403 the target is under a truce: add its id to SKIP_AI and rerun.
"""
import os,re,sys,subprocess,urllib.request,urllib.parse,http.cookiejar
B="http://127.0.0.1:18080"
PW=open(os.environ.get("TESTREALM_PW_FILE",os.path.expanduser("~/ano-realm/.realm_pw"))).read().strip()
cj=http.cookiejar.CookieJar(); op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
class NR(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*a,**k): return None
op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj),NR)
def get(u):
    try: r=op.open(B+u); return r.status,r.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()
def tok(u):
    _,h=get(u); m=re.search(r'name="csrf_token"[^>]*value="([^"]+)"|value="([^"]+)"[^>]*name="csrf_token"|csrf-token" content="([^"]+)"',h); return next(x for x in m.groups() if x)
def post(u,d,page="/provinces"):
    for _ in range(4):
        r=post1(u,d,page)
        if "form expired" not in r[1]: return r
    return r
def post1(u,d,page="/provinces"):
    d=dict(d); d["csrf_token"]=tok(page)
    rq=urllib.request.Request(B+u,urllib.parse.urlencode(d).encode(),{"Origin":B})
    try: r=op.open(rq); return r.status,r.read().decode()
    except urllib.error.HTTPError as e: return e.code,e.read().decode()
def sql(q): return subprocess.run(["docker","exec","anotest-postgres-1","psql","-U","ano_test","-d","ano_test","-Atc",q],capture_output=True,text=True).stdout.strip()
def txt(h): 
    i=h.find("highlight_off"); return re.sub(r"\s+"," ",re.sub(r"<[^>]+>"," ",h[i:i+1200]))[:160] if i>=0 else ""
print("login",post("/login",{"username":"Tester of the Game","password":PW},"/login")[0])
_,h=get("/find_targets"); ai=[x for x in re.findall(r'country/id=(\d+)"[^>]*>[^<]*\[AI\]',h) if x not in set(os.environ.get("SKIP_AI","").split(","))][0]; print("AI",ai)
pid,bid=sql("select province_id||','||building_id from user_buildings where user_id=16 and quantity>1 limit 1").split(",")
sell=lambda: post("/build_structure",{"province_id":pid,"building_id":bid,"quantity":"-1"})
print("declare",post("/declare_war",{"defender":ai,"warType":"Raze","description":"realm test"})[0])
c,h=sell(); print("sell-at-war",c,txt(h))
print("ended",sql("UPDATE wars SET peace_date=extract(epoch from now()),status='ended' WHERE attacker=16 AND peace_date IS NULL RETURNING id"))
c,h=sell(); print("sell-after",c,txt(h))
