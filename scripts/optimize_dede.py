import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from database import get_db_cursor, get_db_connection
from action_loop import purchase_province, purchase_building, purchase_unit

def optimize_account(username):
    print(f"Optimizing account for {username}...")
    with get_db_cursor() as db:
        db.execute("SELECT id FROM users WHERE username = %s", (username,))
        row = db.fetchone()
        if not row:
            print(f"User {username} not found.")
            return
        user_id = row[0]
        print(f"Found user_id: {user_id}")

    # For a few iterations, try to buy provinces, buildings, and military
    for iteration in range(10):
        print(f"Iteration {iteration+1}...")
        
        # 1. Buy Provinces
        for _ in range(50):
            try:
                res = purchase_province(user_id)
                if not res.success:
                    break
                print(f"Bought province: {res.message}")
            except Exception as e:
                break
                
        # 2. Buy Buildings (Economy)
        for b_id in [1, 2, 3]: # Factories, steel mills, etc.
            for _ in range(10):
                try:
                    res = purchase_building(user_id, b_id, quantity=1)
                    if not res.success:
                        break
                    print(f"Bought building {b_id}: {res.message}")
                except Exception:
                    break
                    
        # 3. Buy Military
        for u_id in [1, 2]: # Soldiers, tanks
            for _ in range(10):
                try:
                    res = purchase_unit(user_id, u_id, quantity=100)
                    if not res.success:
                        break
                    print(f"Bought unit {u_id}: {res.message}")
                except Exception:
                    break
                    
    print("Optimization complete!")

if __name__ == "__main__":
    optimize_account("Dede")
