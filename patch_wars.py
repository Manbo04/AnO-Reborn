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
        columns = [
                "aggressor_message VARCHAR(240)",
                "peace_date TIMESTAMP WITH TIME ZONE",
                "attacker_supplies INTEGER DEFAULT 200",
                "defender_supplies INTEGER DEFAULT 200",
                "attacker_morale INTEGER DEFAULT 100",
                "defender_morale INTEGER DEFAULT 100",
                "peace_offer_id INTEGER",
                "status VARCHAR(20) DEFAULT 'active'",
                "winner_id INTEGER",
                "start_date TIMESTAMP WITH TIME ZONE DEFAULT now()",
                "last_visited TIMESTAMP WITH TIME ZONE DEFAULT now()"
            ]
            for col in columns:
                try:
                    QueryHelper.execute(f"ALTER TABLE wars ADD COLUMN IF NOT EXISTS {col};")
                except Exception as e:
                    print(f"Error adding {col}: {e}")
            print("Successfully patched 'wars' table! Added potentially missing columns.")

if __name__ == '__main__':
    run_patch()
