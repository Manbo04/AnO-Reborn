import os
import sys

sys.path.insert(0, '/app')
from database import get_db_cursor

user_id = 8

with get_db_cursor() as db:
    # Stats
    db.execute("INSERT INTO stats (id, location, gold) VALUES (%s, 1, 0) ON CONFLICT DO NOTHING", (user_id,))
    
    # Policies
    db.execute("INSERT INTO policies (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
    
    # user_economy
    db.execute("SELECT resource_id FROM resource_dictionary")
    r_ids = [r[0] for r in db.fetchall()]
    for r_id in r_ids:
        db.execute("INSERT INTO user_economy (user_id, resource_id, quantity) VALUES (%s, %s, 0) ON CONFLICT DO NOTHING", (user_id, r_id))
        
    # user_military
    db.execute("SELECT unit_id FROM unit_dictionary")
    u_ids = [r[0] for r in db.fetchall()]
    for u_id in u_ids:
        db.execute("INSERT INTO user_military (user_id, unit_id, quantity) VALUES (%s, %s, 0) ON CONFLICT DO NOTHING", (user_id, u_id))
        
    # users_statistics
    try:
        db.execute("INSERT INTO users_statistics (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (user_id,))
    except Exception as e:
        print("users_statistics error:", e)

print("Fixed user 8 data.")
