"""Run simple app smoke tests using Flask test client"""

from app import app

paths = ["/", "/login", "/signup", "/market", "/countries", "/intelligence"]

with app.test_client() as c:
    results = {}
    for p in paths:
        try:
            r = c.get(p)
            results[p] = r.status_code
        except Exception as e:
            results[p] = f"EXC: {e}"

print("SMOKE TEST RESULTS")
for p, s in results.items():
    print(f"{p}: {s}")

# exit non-zero if any status not 200, 302, or 308 (some endpoints redirect permanently)
bad = [p for p, s in results.items() if s not in (200, 302, 308)]
if bad:
    print("FAILURES:", bad)
    raise SystemExit(1)
print("All smoke tests OK")
