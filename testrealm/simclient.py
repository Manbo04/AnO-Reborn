"""Per-nation HTTP client for the SIM server (port 18081, DB ano_sim). Refuses any other port."""
import re, requests
BASE = "http://127.0.0.1:18081"
class Nation:
    def __init__(self, username, pw):
        self.s = requests.Session(); self.u = username
        r = self.s.get(BASE + "/login/")
        tok = re.search(r'name="csrf_token" value="([^"]+)"', r.text).group(1)
        r = self.s.post(BASE + "/login/", data={"username": username, "password": pw, "csrf_token": tok}, allow_redirects=False)
        self.ok = r.status_code in (302, 303)
    def post(self, path, data):
        r = self.s.get(BASE + "/country")
        m = re.search(r'name="csrf-token" content="([^"]+)"', r.text) or re.search(r'csrf_token" value="([^"]+)"', r.text)
        d = dict(data); 
        if m: d["csrf_token"] = m.group(1)
        return self.s.post(BASE + path, data=d, allow_redirects=False, headers={"X-CSRFToken": m.group(1) if m else ""})
