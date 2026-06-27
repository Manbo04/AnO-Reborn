import sys
import os
import random
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HEX_DIRECTIONS = [
    (1, 0), (1, -1), (0, -1),
    (-1, 0), (-1, 1), (0, 1)
]

def get_adjacent_coords(x, y):
    return [(x + dx, y + dy) for dx, dy in HEX_DIRECTIONS]

def run_shatter():
    try:
        from app import create_app
        app = create_app()
    except AssertionError:
        from app import app
        
    from database import QueryHelper

    with app.app_context():
        # Get all provinces with coords
        query = "SELECT id, coordinate_x, coordinate_y FROM provinces WHERE coordinate_x IS NOT NULL AND coordinate_y IS NOT NULL"
        rows = QueryHelper.fetch_all(query)
        if not rows:
            print("No provinces to process.")
            return

        print(f"Fetched {len(rows)} provinces with coordinates.")

        # Build coordinate map
        coord_map = {}
        for row in rows:
            coord_map[(row['coordinate_x'], row['coordinate_y'])] = row['id']
            
        provinces = [(row['id'], row['coordinate_x'], row['coordinate_y']) for row in rows]
        
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
            # massive translation vector
            dx = random.randint(-4000, 4000)
            dy = random.randint(-4000, 4000)
            
            for pid, cx, cy in continent:
                new_x = cx + dx
                new_y = cy + dy
                updates.append((new_x, new_y, pid))
                
        # Update db using execute_many
        update_query = "UPDATE provinces SET coordinate_x = %s, coordinate_y = %s WHERE id = %s"
        QueryHelper.execute_many(update_query, updates)
        
        print("Shatter complete! Planets have been separated.")

if __name__ == '__main__':
    run_shatter()
