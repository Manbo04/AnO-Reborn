#!/usr/bin/env python3
"""Grant gold and all resources to a user.
Usage: python grant-resources.py <user_id> <gold_amount> <resource_amount>

Example (give 100B gold and 1M resources):
  python grant-resources.py 8 100000000000 1000000

Intended to run via Railway:
  railway run python scripts/grant-resources.py 8 100000000000 1000000
"""

import os
import sys
from urllib.parse import urlparse
from dotenv import load_dotenv
import psycopg2

load_dotenv()

if len(sys.argv) != 4:
    print("Usage: python grant-resources.py <user_id> <gold_amount> <resource_amount>")
    sys.exit(1)

user_id = sys.argv[1]
try:
    gold_amount = int(sys.argv[2])
    resource_amount = int(sys.argv[3])
except ValueError:
    print("gold_amount and resource_amount must be integers")
    sys.exit(1)

# Build connection params from DATABASE_PUBLIC_URL/DATABASE_URL if PG_* not set
db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
if db_url:
    parsed = urlparse(db_url)
    db_params = {
        "database": parsed.path[1:],
        "user": parsed.username,
        "password": parsed.password,
        "host": parsed.hostname,
        "port": parsed.port,
        "sslmode": "require",
    }
else:
    db_params = {
        "database": os.getenv("PG_DATABASE"),
        "user": os.getenv("PG_USER"),
        "password": os.getenv("PG_PASSWORD"),
        "host": os.getenv("PG_HOST"),
        "port": os.getenv("PG_PORT"),
    }

conn = psycopg2.connect(**db_params)
db = conn.cursor()

resources = [
    "rations",
    "oil",
    "coal",
    "uranium",
    "bauxite",
    "lead",
    "copper",
    "iron",
    "lumber",
    "components",
    "steel",
    "consumer_goods",
    "aluminium",
    "gasoline",
    "ammunition",
]

try:
    # Add gold
    db.execute("UPDATE stats SET gold = gold + %s WHERE id=%s", (gold_amount, user_id))

    # Add each resource
    for res in resources:
        db.execute(
            f"UPDATE resources SET {res} = {res} + %s WHERE id=%s",
            (resource_amount, user_id),
        )

    conn.commit()
    print(
        f"Granted user {user_id}: +{gold_amount} gold, +{resource_amount} to each resource"
    )
except Exception as e:
    conn.rollback()
    print(f"Error: {e}")
    sys.exit(1)
finally:
    conn.close()
