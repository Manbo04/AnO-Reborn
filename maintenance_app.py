"""Standalone maintenance-mode server for affairsandorder.org.

Deliberately NOT the real Flask app (app.py/wsgi.py) -- this has zero
authentication, zero session handling, zero database access, and zero shared
code with the app under investigation for the account cross-contamination
bug. Its only job is to serve one static page with a countdown timer while
that bug is being traced, so the domain isn't dark and no real player data
or session logic is exposed in the meantime.

Point Railway's `web` service start command at this file instead of
scripts/start_production.sh to activate maintenance mode; point it back to
restore the real app.
"""
import os
from datetime import datetime, timedelta, timezone

from flask import Flask, Response, request
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# Same ProxyFix config as the real app.py -- added 2026-09-23 purely to test
# a specific hypothesis: the real app trusts exactly one proxy hop
# (x_for=1) for X-Forwarded-For, but this domain is Cloudflare-fronted in
# front of Railway's own edge (confirmed via response headers carrying both
# `server: cloudflare` and `x-railway-edge`) -- a genuine two-hop chain. If
# x_for=1 resolves to the wrong IP under two real hops, every "which real
# player is this" signal downstream (login_events, identity diagnostics,
# rate limiting) could be silently wrong. This endpoint has zero auth/
# session/DB code -- read-only diagnostic only.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)


@app.route("/debug-ip")
def debug_ip():
    return {
        "remote_addr_after_proxyfix": request.remote_addr,
        "raw_x_forwarded_for_header": request.headers.get("X-Forwarded-For"),
        "cf_connecting_ip_header": request.headers.get("CF-Connecting-IP"),
        "true_client_ip_header": request.headers.get("True-Client-IP"),
    }, 200

_DEFAULT_DEADLINE = "2026-09-23T16:38:32Z"
DEADLINE_ISO = os.environ.get("MAINTENANCE_DEADLINE", _DEFAULT_DEADLINE)

PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Affairs and Order &mdash; Under Maintenance</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    background: #0b0f1a; color: #e8ecf4;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    padding: 24px;
  }}
  .card {{
    max-width: 560px; width: 100%; text-align: center;
    background: #131a2b; border: 1px solid #232d47; border-radius: 16px;
    padding: 40px 32px;
  }}
  h1 {{ font-size: 1.5rem; margin: 0 0 12px; }}
  p {{ color: #9aa5c1; line-height: 1.5; margin: 0 0 28px; }}
  .timer {{
    font-variant-numeric: tabular-nums;
    font-size: 2.4rem; font-weight: 700; letter-spacing: 0.04em;
    color: #7dd3fc; margin-bottom: 8px;
  }}
  .label {{ color: #66708c; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.08em; }}
</style>
</head>
<body>
  <div class="card">
    <h1>Affairs and Order is temporarily offline</h1>
    <p>We found a real account-security issue and took the game down while we fix it properly.
       No action is needed from you &mdash; your nation is safe and untouched.</p>
    <div class="timer" id="timer">--:--:--</div>
    <div class="label">estimated time remaining</div>
  </div>
  <script>
    var deadline = new Date("{deadline}").getTime();
    function tick() {{
      var diff = Math.max(0, deadline - Date.now());
      var h = Math.floor(diff / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var s = Math.floor((diff % 60000) / 1000);
      function pad(n) {{ return String(n).padStart(2, "0"); }}
      document.getElementById("timer").textContent = pad(h) + ":" + pad(m) + ":" + pad(s);
    }}
    tick();
    setInterval(tick, 1000);
  </script>
</body>
</html>
""".format(deadline=DEADLINE_ISO)


@app.route("/health")
def health():
    return {"status": "maintenance"}, 200


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def catch_all(path):
    return Response(PAGE, status=503, mimetype="text/html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
