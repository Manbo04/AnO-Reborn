#!/usr/bin/env python3
"""Delete all test bot accounts from the database."""
import os
import psycopg2

# Use public URL for external access
os.environ[
    "DATABASE_URL"
] = "postgresql://postgres:yUhDEaGngcGPlRPrfqGIofVDwvRRXvcz@interchange.proxy.rlwy.net:41077/railway"

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# Specific test account IDs identified from database
# Excluding: 9999 (market bot), 9998 (supply bot)
# Round 3: v_* accounts
test_ids = [735, 741, 751, 761, 769]
print(f"Deleting {len(test_ids)} test accounts: {test_ids}")

if not test_ids:
    print("No test accounts found.")
    conn.close()
    exit(0)

# Delete proInfra for provinces owned by test users
cur.execute("SELECT id FROM provinces WHERE userId = ANY(%s)", (test_ids,))
province_ids = [row[0] for row in cur.fetchall()]
if province_ids:
    cur.execute("DELETE FROM proInfra WHERE id = ANY(%s)", (province_ids,))
    print(f"Deleted {cur.rowcount} proInfra records")

# Delete from related tables
tables = [
    ("provinces", "userId"),
    ("stats", "id"),
    ("resources", "id"),
    ("military", "id"),
    ("coalitions", "userId"),
    ("offers", "user_id"),
    ("trades", "offerer"),
    ("trades", "offeree"),
    ("wars", "attacker"),
    ("wars", "defender"),
    ("revenue", "user_id"),
    ("policies", "user_id"),
]

for table, col in tables:
    try:
        cur.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (test_ids,))
        if cur.rowcount > 0:
            print(f"Deleted {cur.rowcount} from {table}")
    except Exception as e:
        print(f"Skipped {table}: {e}")
        conn.rollback()

# Finally delete the users
cur.execute("DELETE FROM users WHERE id = ANY(%s)", (test_ids,))
print(f"Deleted {cur.rowcount} test user accounts")

conn.commit()
print("Done!")
conn.close()
