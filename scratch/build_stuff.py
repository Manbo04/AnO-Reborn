import os
import json
import psycopg2
from urllib.parse import urlparse

def main():
    db_url = os.getenv("DATABASE_PUBLIC_URL") or os.getenv("DATABASE_URL")
    if "?" in db_url: db_url += "&sslmode=disable"
    else: db_url += "?sslmode=disable"
    
    conn = psycopg2.connect(db_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            # Get the user's ID. Let's assume user ID 1.
            cur.execute("SELECT id FROM provinces WHERE userId=1 LIMIT 1;")
            row = cur.fetchone()
            if not row:
                print("No province found for user 1")
                return
            prov_id = row[0]
            
            # Fetch current buildings
            cur.execute("SELECT buildings FROM provinces WHERE id=%s;", (prov_id,))
            b_row = cur.fetchone()
            buildings = b_row[0] if b_row and b_row[0] else {}
            if isinstance(buildings, str):
                buildings = json.loads(buildings)
                
            # Add essential buildings
            buildings["coal_burners"] = buildings.get("coal_burners", 0) + 10
            buildings["coal_mines"] = buildings.get("coal_mines", 0) + 10
            buildings["lumber_mills"] = buildings.get("lumber_mills", 0) + 10
            buildings["farms"] = buildings.get("farms", 0) + 10
            buildings["iron_mines"] = buildings.get("iron_mines", 0) + 10
            buildings["pumpjacks"] = buildings.get("pumpjacks", 0) + 10
            
            cur.execute("UPDATE provinces SET buildings=%s WHERE id=%s;", (json.dumps(buildings), prov_id))
            print(f"Updated buildings for province {prov_id}!")
            
    except Exception as e:
        print("Error:", e)
    finally:
        conn.close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
