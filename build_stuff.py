import sys
import os

# Add current dir to python path so we can import app modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ["PGSSLMODE"] = "disable"

from app import app
from database import get_request_cursor

def main():
    with app.app_context():
        with get_request_cursor() as cur:
            cur.execute("SELECT id, provinceName FROM provinces WHERE userId = 1")
            provinces = cur.fetchall()
            
            if not provinces:
                print("No provinces found.")
                return
                
            for prov in provinces:
                prov_id = prov['id']
                print(f"Adding buildings to province {prov['provincename']} (ID: {prov_id})")
                
                # Add buildings
                buildings = {
                    'farm': 10,
                    'coal_power_plant': 5,
                    'coal_mine': 10,
                    'distribution_center': 5,
                    'lumber_camp': 10,
                    'iron_mine': 5,
                    'bauxite_mine': 5,
                    'steel_mill': 2,
                    'aluminium_refinery': 2,
                    'primary_school': 5,
                    'high_school': 5
                }
                
                for name, qty in buildings.items():
                    cur.execute("""
                        INSERT INTO buildings (province_id, name, qty) 
                        VALUES (%s, %s, %s)
                        ON CONFLICT (province_id, name) DO UPDATE SET qty = buildings.qty + EXCLUDED.qty
                    """, (prov_id, name, qty))
                    
            # Grant some resources to jumpstart them too
            cur.execute("UPDATE stats SET gold = gold + 50000000 WHERE id = 1")
            cur.execute("UPDATE user_economy SET quantity = quantity + 1000000 WHERE user_id = 1")
            
        print("Done building stuff.")

if __name__ == '__main__':
    main()
