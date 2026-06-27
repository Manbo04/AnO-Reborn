import os
import random
import psycopg2
from dotenv import load_dotenv

load_dotenv()
DATABASE_URL = os.environ.get("DATABASE_URL")

# Hex grid adjacent directions (Axial coordinates)
HEX_DIRECTIONS = [
    (1, 0), (1, -1), (0, -1),
    (-1, 0), (-1, 1), (0, 1)
]

def get_adjacent_coords(x, y):
    return [(x + dx, y + dy) for dx, dy in HEX_DIRECTIONS]

def seed_province_coordinates():
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    print("Fetching provinces...")
    # Group provinces by user_id
    cur.execute("SELECT id, user_id FROM provinces WHERE coordinate_x IS NULL OR coordinate_y IS NULL ORDER BY user_id, id")
    provinces = cur.fetchall()

    if not provinces:
        print("No provinces need updating.")
        return

    # Track occupied tiles to avoid collisions
    cur.execute("SELECT coordinate_x, coordinate_y FROM provinces WHERE coordinate_x IS NOT NULL")
    occupied = set(cur.fetchall())

    user_provinces = {}
    for prov_id, user_id in provinces:
        if user_id not in user_provinces:
            user_provinces[user_id] = []
        user_provinces[user_id].append(prov_id)

    print(f"Assigning coordinates for {len(provinces)} provinces across {len(user_provinces)} players...")

    updates = []
    
    for user_id, prov_ids in user_provinces.items():
        # Pick a random starting point for the user's first province far away from others
        while True:
            # Drop them somewhere in a large 50x50 grid initially
            start_x = random.randint(-25, 25)
            start_y = random.randint(-25, 25)
            if (start_x, start_y) not in occupied:
                break
                
        user_occupied = set()
        user_frontier = [(start_x, start_y)]
        
        for prov_id in prov_ids:
            # Find the next available adjacent tile
            placed = False
            # Check frontier until we find an empty spot
            while user_frontier and not placed:
                cx, cy = user_frontier.pop(0)
                if (cx, cy) not in occupied:
                    # Place province here
                    occupied.add((cx, cy))
                    user_occupied.add((cx, cy))
                    updates.append((cx, cy, prov_id))
                    
                    # Add all adjacent tiles to the frontier
                    for ax, ay in get_adjacent_coords(cx, cy):
                        if (ax, ay) not in occupied and (ax, ay) not in user_occupied:
                            user_frontier.append((ax, ay))
                    placed = True

    # Batch update the provinces
    print("Updating database...")
    from psycopg2.extras import execute_values
    execute_values(
        cur,
        "UPDATE provinces SET coordinate_x = data.x, coordinate_y = data.y FROM (VALUES %s) AS data (x, y, id) WHERE provinces.id = data.id",
        updates
    )
    
    conn.commit()
    cur.close()
    conn.close()
    print("Successfully seeded province coordinates!")

if __name__ == "__main__":
    seed_province_coordinates()
