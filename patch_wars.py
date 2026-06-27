import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_patch():
    try:
        from app import create_app
        app = create_app()
    except AssertionError:
        from app import app
        
    from database import QueryHelper

    with app.app_context():
        try:
            QueryHelper.execute("ALTER TABLE wars ADD COLUMN IF NOT EXISTS aggressor_message VARCHAR(240);")
            print("Successfully patched 'wars' table! Added 'aggressor_message' column.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == '__main__':
    run_patch()
