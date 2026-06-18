import os
import json
import psycopg2
from urllib.parse import urlparse

def main():
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if "?" in db_url: db_url += "&sslmode=disable"
    else: db_url += "?sslmode=disable"
    
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT buildings FROM provinces WHERE userId=1 LIMIT 1;")
            res = cur.fetchone()
            print("Buildings for user 1:", res[0])
    except Exception as e:
        print("Error:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
