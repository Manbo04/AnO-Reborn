import os
import psycopg2
import config

DATABASE_URL = config.get_database_url()
if not DATABASE_URL:
    print("No DATABASE_URL")
else:
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM provinces;")
        print("Provinces:", cur.fetchone()[0])
        cur.execute("SELECT COUNT(*) FROM users;")
        print("Users:", cur.fetchone()[0])
    except Exception as e:
        print("Error:", e)
