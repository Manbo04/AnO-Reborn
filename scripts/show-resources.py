#!/usr/bin/env python3
"""Show resources and gold for a given user id.
Usage: python show-resources.py <user_id>
Use with `railway run python scripts/show-resources.py <id>` in production.
"""

import os
import sys
from urllib.parse import urlparse
from dotenv import load_dotenv
import psycopg2

load_dotenv()

if len(sys.argv) != 2:
    print("Usage: python show-resources.py <user_id>")
    sys.exit(1)

user_id = sys.argv[1]

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

# Fetch gold
db.execute("SELECT gold FROM stats WHERE id=%s", (user_id,))
gold_row = db.fetchone()

# Fetch resources
resource_fields = [
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
fields_sql = ", ".join(resource_fields)
db.execute(f"SELECT {fields_sql} FROM resources WHERE id=%s", (user_id,))
res_row = db.fetchone()

print(f"User ID: {user_id}")
if gold_row:
    print(f"Gold: {gold_row[0]}")
else:
    print("Gold: <not found>")

if res_row:
    for name, val in zip(resource_fields, res_row):
        print(f"{name}: {val}")
else:
    print("Resources: <not found>")

conn.close()
