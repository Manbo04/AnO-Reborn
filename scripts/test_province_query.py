#!/usr/bin/env python
import os
import sys

# Use public URL for external access
os.environ["DATABASE_URL"] = os.environ.get(
    "DATABASE_PUBLIC_URL",
    "postgresql://postgres:yUhDEaGngcGPlRPrfqGIofVDwvRRXvcz@interchange.proxy.rlwy.net:41077/railway",
)

from psycopg2.extras import RealDictCursor
from database import get_db_connection

pId = sys.argv[1] if len(sys.argv) > 1 else 296

with get_db_connection() as conn:
    db = conn.cursor(cursor_factory=RealDictCursor)
    sql = """SELECT p.id, p.userId AS user, p.provinceName AS name, p.population,
        p.pollution, p.happiness, p.productivity, p.consumer_spending,
        CAST(p.citycount AS INTEGER) as citycount,
        p.land, p.energy AS electricity,
        s.location, r.consumer_goods, r.rations, pi.*
        FROM provinces p
        LEFT JOIN stats s ON p.userId = s.id
        LEFT JOIN resources r ON p.userId = r.id
        LEFT JOIN proInfra pi ON p.id = pi.id
        WHERE p.id = %s"""
    db.execute(sql, (pId,))
    result = db.fetchone()
    if result:
        print("Query OK")
        print("Keys:", list(result.keys())[:15])
        print("Province name:", result.get("name"))
        print("Population:", result.get("population"))
    else:
        print("No result for province", pId)
