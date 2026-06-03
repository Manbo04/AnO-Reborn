import os
import psycopg2
from psycopg2.extras import DictCursor

def validate():
    db_url = os.getenv("DATABASE_URL")
    print(f"Connecting to {db_url}...")
    try:
        conn = psycopg2.connect(db_url)
        with conn.cursor(cursor_factory=DictCursor) as cur:
            queries = [
                ("User Count", "SELECT COUNT(*) AS count FROM \"User\";"),
                ("Users View Count", "SELECT COUNT(*) AS count FROM users;"),
                ("Province Count", "SELECT COUNT(*) AS count FROM \"Province\";"),
                ("Provinces View Count", "SELECT COUNT(*) AS count FROM provinces;"),
                ("Recent Users", "SELECT id, username, auth_type FROM users ORDER BY id DESC LIMIT 20;")
            ]
            for label, sql in queries:
                print(f"--- {label} ---")
                cur.execute(sql)
                if "SELECT id" in sql:
                    rows = cur.fetchall()
                    for row in rows:
                        print(dict(row))
                else:
                    print(cur.fetchone()['count'])
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    validate()
