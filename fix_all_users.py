import os
import sys

sys.path.insert(0, '/app')
from database import get_db_cursor

with get_db_cursor() as db:
    # Get all users
    db.execute("SELECT id FROM users")
    users = [r[0] for r in db.fetchall()]
    
    # Pre-fetch dictionaries
    db.execute("SELECT resource_id FROM resource_dictionary")
    r_ids = [r[0] for r in db.fetchall()]
    
    db.execute("SELECT unit_id FROM unit_dictionary")
    u_ids = [r[0] for r in db.fetchall()]

    for user_id in users:
        # Stats
        db.execute("INSERT INTO stats (id, location, gold) VALUES (%s, 1, 0) ON CONFLICT DO NOTHING", (user_id,))
        
        # Policies
        db.execute("INSERT INTO policies (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        
        # user_economy
        for r_id in r_ids:
            db.execute("INSERT INTO user_economy (user_id, resource_id, quantity) VALUES (%s, %s, 0) ON CONFLICT DO NOTHING", (user_id, r_id))
            
        # user_military
        for u_id in u_ids:
            db.execute("INSERT INTO user_military (user_id, unit_id, quantity) VALUES (%s, %s, 0) ON CONFLICT DO NOTHING", (user_id, u_id))
            
        # users_statistics
        try:
            db.execute("INSERT INTO users_statistics (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
        except Exception as e:
            pass

print("Fixed missing data for all users.")
