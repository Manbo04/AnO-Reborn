import sys
import os
import random
from collections import deque

# Add the project directory to sys.path so we can import app and database
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from database import QueryHelper

HEX_DIRECTIONS = [
    (1, 0), (1, -1), (0, -1),
    (-1, 0), (-1, 1), (0, 1)
]

def get_adjacent_coords(x, y):
    return [(x + dx, y + dy) for dx, dy in HEX_DIRECTIONS]

def run_shatter():
    from dotenv import load_dotenv
    load_dotenv()
    from database import get_db_connection
    import psycopg2.extras

    with get_db_connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # Get all provinces with coords
                cur.execute("SELECT id, x, y FROM provinces WHERE x IS NOT NULL AND y IS NOT NULL")
                rows = cur.fetchall()
                if not rows:
                    print("No provinces to process.")
                    return

                print(f"Fetched {len(rows)} provinces with coordinates.")

                # Build coordinate map
                coord_map = {}
                for row in rows:
                    coord_map[(row['x'], row['y'])] = row['id']
                    
                provinces = [(row['id'], row['x'], row['y']) for row in rows]
                
                visited = set()
                continents = []
                
                # BFS to find continents
                for prov in provinces:
                    pid, px, py = prov
                    if pid in visited:
                        continue
                    
                    # Start new continent
                    continent = []
                    queue = deque([prov])
                    visited.add(pid)
                    
                    while queue:
                        curr_id, cx, cy = queue.popleft()
                        continent.append((curr_id, cx, cy))
                        
                        for ax, ay in get_adjacent_coords(cx, cy):
                            if (ax, ay) in coord_map:
                                adj_id = coord_map[(ax, ay)]
                                if adj_id not in visited:
                                    visited.add(adj_id)
                                    queue.append((adj_id, ax, ay))
                                    
                    continents.append(continent)
                    
                print(f"Found {len(continents)} continents.")
                
                # Generate translation for each continent and prepare updates
                updates = []
                for i, continent in enumerate(continents):
                    dx = random.randint(-4000, 4000)
                    dy = random.randint(-4000, 4000)
                    
                    for pid, cx, cy in continent:
                        new_x = cx + dx
                        new_y = cy + dy
                        updates.append((new_x, new_y, pid))
                        
                # Update db
                cur.executemany("UPDATE provinces SET x = %s, y = %s WHERE id = %s", updates)
                conn.commit()
                
                print("Shatter complete! Planets have been separated.")

if __name__ == '__main__':
    run_shatter()
