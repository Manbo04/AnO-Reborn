import subprocess
import os

db_url = "postgresql://postgres:yUhDEaGngcGPlRPrfqGIofVDwvRRXvcz@postgres-check-snapshot.railway.internal:5432/railway"
print(f"Connecting to {db_url}...")

try:
    res = subprocess.run(["psql", db_url, "-c", "SELECT COUNT(*) FROM \"User\";"], capture_output=True, text=True, timeout=30)
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
except Exception as e:
    print("Error:", e)
