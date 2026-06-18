import os
import sys
import json

# Set up environment
os.chdir("/Users/dede/AnO-Reborn")
sys.path.append("/Users/dede/AnO-Reborn")

from database import reuse_or_new_cursor
from psycopg2.extras import RealDictCursor
import countries

USER_ID = 1

def main():
    print("--- get_revenue(1) ---")
    rev = countries.get_revenue(USER_ID)
    print(json.dumps(rev, indent=2))

    with reuse_or_new_cursor(cursor_factory=RealDictCursor) as db:
        print("\n--- stats.gold ---")
        db.execute("SELECT gold FROM stats WHERE id = %s", (USER_ID,))
        stats = db.fetchone()
        print(dict(stats) if stats else "None")

        print("\n--- user_buildings ---")
        db.execute("""
            SELECT ub.province_id, bd.name, ub.quantity
            FROM user_buildings ub
            JOIN building_dictionary bd ON bd.building_id = ub.building_id
            WHERE ub.user_id = %s
        """, (USER_ID,))
        buildings = db.fetchall()
        for b in buildings:
            print(dict(b))

if __name__ == "__main__":
    main()
