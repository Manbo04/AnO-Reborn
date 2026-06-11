import os
import sys

sys.path.insert(0, '/app')

from app import app
from database import get_db_cursor

# We need to find the user ID for Mohammad or any user that throws 500
with app.app_context():
    with get_db_cursor() as db:
        db.execute("SELECT id, username FROM users WHERE username ILIKE '%mohammad%'")
        users = db.fetchall()
        print("Found users:", users)

    client = app.test_client()
    for u in users:
        uid = u[0]
        uname = u[1]
        print(f"\n--- Testing /account for user {uid} ({uname}) ---")
        with client.session_transaction() as sess:
            sess["user_id"] = uid
        try:
            response = client.get("/account")
            print("Status:", response.status_code)
            if response.status_code == 500:
                print("Body:", response.data.decode("utf-8")[:500])
        except Exception as e:
            import traceback
            traceback.print_exc()

