from dotenv import load_dotenv
load_dotenv()
from database import db_pool
conn = db_pool.get_connection()
c = conn.cursor()
c.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
for r in c.fetchall(): print(r[0])
