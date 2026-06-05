import sys
sys.path.insert(0, '/Users/dede/AnO-Reborn')
from app import app
from database import get_request_cursor

with app.app_context():
    with get_request_cursor() as db:
        db.execute("SELECT 1 AS vote_option, 2 AS count")
        print("fetchall:", db.fetchall())
        
        db.execute("SELECT 1 AS vote_option")
        row = db.fetchone()
        print("fetchone:", row)
        print("row[0]:", row[0] if row else None)
