# Script for giving resources to players
import os
from urllib.parse import urlparse
from dotenv import load_dotenv
import psycopg2
import sys

load_dotenv()

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

resource = sys.argv[1]
amount = sys.argv[2]
user_id = sys.argv[3]

if resource == "all":
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

    for resource in resources:
        resource_update = (
            f"UPDATE resources SET {resource}={resource}" + "+%s WHERE id=%s"
        )
        db.execute(
            resource_update,
            (
                amount,
                user_id,
            ),
        )

    db.execute("UPDATE stats SET gold=gold+%s WHERE id=%s", (amount, user_id))

    conn.commit()
    conn.close()
else:
    print("Unrecognized resource")
