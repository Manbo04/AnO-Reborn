from database import get_db_connection
import sys

try:
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, username, email, verification_token, token_created_at, is_verified FROM users ORDER BY id DESC LIMIT 5")
    rows = cur.fetchall()
    for r in rows:
        print(r)
except Exception as e:
    print(f"Error: {e}")
