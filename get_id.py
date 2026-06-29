from dotenv import load_dotenv
load_dotenv()
from database import get_db_connection
with get_db_connection() as conn:
  c = conn.cursor()
  c.execute("SELECT id FROM users WHERE username='Terra Homeworld'")
  print(c.fetchone())
