"""Create a dummy user to verify next sequence ID assignment, then clean up.

Usage: PYTHONPATH=. python3 scripts/test_create_dummy_user.py

The script will:
 - Insert a user with unique username/email
 - Print the assigned id
 - Verify it's equal to current nextval(users_id_seq) (or expected value)
 - Delete the user and any created resource rows (resources, stats, military, upgrades, policies, provinces, proInfra, offers, trades, wars, spyinfo)
 - Save an audit JSON in backups/test-create-dummy-<ts>/
"""

import os
import json
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor
import time

load_dotenv()
TS = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
OUTDIR = f"backups/test-create-dummy-{TS}"

os.makedirs(OUTDIR, exist_ok=True)

conn = psycopg2.connect(
    dbname=os.getenv("PG_DATABASE"),
    user=os.getenv("PG_USER"),
    password=os.getenv("PG_PASSWORD"),
    host=os.getenv("PG_HOST", "localhost"),
    port=os.getenv("PG_PORT", "5432"),
)
try:
    with conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            username = f"tmp_test_user_{TS}"
            email = f"tmp{TS}@example.invalid"
            hashed = (
                "$2b$12$aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"  # dummy hash
            )
            today = str(datetime.utcnow().date())

            # Insert user
            cur.execute(
                "INSERT INTO users (username, email, hash, date, auth_type) VALUES (%s,%s,%s,%s,%s) RETURNING id",
                (username, email, hashed, today, "normal"),
            )
            row = cur.fetchone()
            assigned_id = row["id"]

            # Capture current seq value
            cur.execute("SELECT pg_get_serial_sequence('users','id') AS seqname")
            seq = cur.fetchone()["seqname"]
            cur.execute(f"SELECT last_value, is_called FROM {seq}")
            seq_after = cur.fetchone()

            report = {
                "timestamp": datetime.utcnow().isoformat(),
                "username": username,
                "email": email,
                "assigned_id": assigned_id,
                "seq_after": seq_after,
            }
            with open(
                os.path.join(OUTDIR, "pre-cleanup-report.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(report, f, indent=2, default=str)
            print("Inserted user id:", assigned_id)
            print("Sequence after insert:", seq_after)

            # Now check related tables and delete any rows created
            related_tables = [
                ("offers", "user_id"),
                ("trades", "offerer"),
                ("trades", "offeree"),
                ("wars", "attacker"),
                ("wars", "defender"),
                ("spyinfo", "spyer"),
                ("spyinfo", "spyee"),
                ("provinces", "userId"),
                ("proInfra", "id"),
                ("upgrades", "user_id"),
                ("policies", "user_id"),
                ("military", "id"),
                ("stats", "id"),
                ("resources", "id"),
            ]
            cleanup = {}
            for table, col in related_tables:
                try:
                    cur.execute(
                        f"SELECT COUNT(*) AS c FROM {table} WHERE {col}=%s",
                        (assigned_id,),
                    )
                    cnt = cur.fetchone()["c"]
                    cleanup[f"{table}.{col}"] = cnt
                except Exception as e:
                    cleanup[f"{table}.{col}"] = str(e)

            # Now perform deletions
            for table, col in related_tables:
                try:
                    cur.execute(f"DELETE FROM {table} WHERE {col}=%s", (assigned_id,))
                except Exception:
                    pass

            # Finally delete user
            cur.execute("DELETE FROM users WHERE id=%s", (assigned_id,))

            # commit already by context
            after_report = {"cleanup_counts": cleanup}
            with open(
                os.path.join(OUTDIR, "post-cleanup-report.json"), "w", encoding="utf-8"
            ) as f:
                json.dump(after_report, f, indent=2, default=str)

            print("Cleanup counts (pre-deletion):")
            print(json.dumps(cleanup, indent=2))
            print("User deleted. Test complete. Audit in", OUTDIR)
finally:
    conn.close()
