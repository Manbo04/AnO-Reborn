import os
import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")
conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

cur.execute("SELECT id, username, gold FROM stats WHERE username='glob'")
print("Glob stats:", cur.fetchone())

cur.execute("SELECT id, land, citycount FROM provinces WHERE userId=(SELECT id FROM stats WHERE username='glob')")
print("Glob provinces:", cur.fetchall())

cur.execute("SELECT r.name, ue.quantity FROM user_economy ue JOIN resource_dictionary r ON r.resource_id=ue.resource_id WHERE ue.user_id=(SELECT id FROM stats WHERE username='glob')")
print("Glob resources:", cur.fetchall())

cur.execute("SELECT name FROM building_dictionary")
names = [r[0] for r in cur.fetchall()]
print(names)
