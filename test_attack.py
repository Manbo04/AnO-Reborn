from app import app
from database import get_request_cursor
with app.test_request_context('/'):
    with get_request_cursor() as db:
        pass
print("Test complete.")
