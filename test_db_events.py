import psycopg2
import os

conn_str = os.environ.get("DATABASE_URL", "postgresql://localhost/postgres")
try:
    conn = psycopg2.connect(conn_str)
    cur = conn.cursor()
    cur.execute("SELECT * FROM interactive_events LIMIT 5;")
    rows = cur.fetchall()
    print(rows)
except Exception as e:
    print(e)
