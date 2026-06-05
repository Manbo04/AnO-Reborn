from app import app
from database import get_request_cursor
with app.app_context():
    with get_request_cursor() as db:
        db.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users'")
        print(db.fetchall())
