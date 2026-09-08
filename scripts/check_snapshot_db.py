import os
import subprocess

db_url = os.environ["SNAPSHOT_CHECK_DATABASE_URL"]
print("Connecting to snapshot-check database...")

try:
    res = subprocess.run(["psql", db_url, "-c", "SELECT COUNT(*) FROM \"User\";"], capture_output=True, text=True, timeout=30)
    print("STDOUT:", res.stdout)
    print("STDERR:", res.stderr)
except Exception as e:
    print("Error:", e)
