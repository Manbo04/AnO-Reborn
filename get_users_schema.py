import psycopg2
conn = psycopg2.connect("postgresql://localhost")
cur = conn.cursor()
cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users';")
for row in cur.fetchall():
    print(row)
