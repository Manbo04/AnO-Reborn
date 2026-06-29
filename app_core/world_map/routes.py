from flask import Blueprint, render_template, session, jsonify
from helpers import login_required
from .services import WorldMapService

bp = Blueprint("world_map", __name__)

@bp.route("/world_map")
@login_required
def world_map_view():
    """Render the PixiJS Interactive World Map."""
    user_id = session.get("user_id")
    user_col = WorldMapService.get_user_coalition(user_id)
    
    user_coalition_id = user_col[0] if user_col else None
    user_coalition_name = user_col[1] if user_col else None

    return render_template(
        "world_map.html", 
        user_coalition_id=user_coalition_id,
        user_coalition_name=user_coalition_name
    )

@bp.route("/api/world_map/nodes", methods=["GET"])
@login_required
def get_nodes():
    """Return JSON payload of all nodes, their ownership, and active battles."""
    nodes = WorldMapService.get_all_nodes()
    return jsonify({"status": "success", "nodes": nodes})

from extensions import limiter

@bp.route("/api/world_map/nodes/<int:node_id>/attack", methods=["POST"])
@login_required
@limiter.limit("10 per minute")
def declare_siege(node_id):
    """Declare an attack on a node. Costs Intel."""
    user_id = session.get("user_id")
    result = WorldMapService.declare_siege(user_id, node_id)
    return jsonify(result)

@bp.route("/lore_map")
@login_required
def lore_map():
    """Render the HTML/CSS infinite canvas hex map for provinces."""
    return render_template("lore_map.html")

@bp.route("/api/province_map/nodes", methods=["GET"])
@login_required
def get_province_map_nodes():
    """Return all provinces to plot on the hex map."""
    from database import get_request_cursor
    with get_request_cursor(read_only=True) as db:
        db.execute("""
            SELECT p.id, p.provinceName as name, p.userId as user_id, u.username, 
                   COALESCE(p.coordinate_x, 0) as coordinate_x, 
                   COALESCE(p.coordinate_y, 0) as coordinate_y,
                   COALESCE(p.pop_working, 0) + COALESCE(p.pop_children, 0) + COALESCE(p.pop_elderly, 0) as population, 
                   0.0 as tax_rate, 
                   0.0 as unrest, 
                   0.0 as corruption
            FROM provinces p
            JOIN users u ON p.userId = u.id
            WHERE p.coordinate_x IS NOT NULL AND p.coordinate_y IS NOT NULL
        """)
        rows = db.fetchall()
        
    provinces = []
    for r in rows:
        provinces.append({
            "id": int(r[0]) if r[0] is not None else 0,
            "name": str(r[1]) if r[1] is not None else "",
            "user_id": int(r[2]) if r[2] is not None else None,
            "username": str(r[3]) if r[3] is not None else None,
            "x": float(r[4]) if r[4] is not None else 0.0,
            "y": float(r[5]) if r[5] is not None else 0.0,
            "population": int(r[6]) if r[6] is not None else 0,
            "tax_rate": float(r[7]) if r[7] is not None else 0.0,
            "unrest": float(r[8]) if r[8] is not None else 0.0,
            "corruption": float(r[9]) if r[9] is not None else 0.0
        })
    import math
    import random

    # 1. Group by user first
    user_clusters = {}
    for p in provinces:
        uid = p["user_id"]
        if uid not in user_clusters:
            user_clusters[uid] = []
        user_clusters[uid].append(p)

    planets_data = []
    for uid, cluster_provinces in user_clusters.items():
        sum_x = sum(p["x"] for p in cluster_provinces)
        sum_y = sum(p["y"] for p in cluster_provinces)
        cx = sum_x / len(cluster_provinces)
        cy = sum_y / len(cluster_provinces)
        max_dist = max([math.hypot(p["x"] - cx, p["y"] - cy) for p in cluster_provinces] + [0])
        
        radius = max_dist * 60 + 200
        planets_data.append({
            "uid": uid,
            "cx": cx,
            "cy": cy,
            "radius": radius,
            "provinces": cluster_provinces
        })

    # 2. Merge overlapping planets iteratively
    merged = True
    while merged:
        merged = False
        for i in range(len(planets_data)):
            for j in range(i + 1, len(planets_data)):
                p1 = planets_data[i]
                p2 = planets_data[j]
                
                # Approximate pixel distance between centroids (Hex size ~ 50, spacing ~ 1)
                dist_coords = math.hypot(p1["cx"] - p2["cx"], p1["cy"] - p2["cy"])
                dist_pixels = dist_coords * 50 
                
                # If they overlap, merge them
                if dist_pixels < (p1["radius"] + p2["radius"]):
                    p1["provinces"].extend(p2["provinces"])
                    
                    sum_x = sum(p["x"] for p in p1["provinces"])
                    sum_y = sum(p["y"] for p in p1["provinces"])
                    p1["cx"] = sum_x / len(p1["provinces"])
                    p1["cy"] = sum_y / len(p1["provinces"])
                    p1["max_dist"] = max([math.hypot(p["x"] - p1["cx"], p["y"] - p1["cy"]) for p in p1["provinces"]] + [0])
                    p1["radius"] = p1["max_dist"] * 60 + 200
                    
                    planets_data.pop(j)
                    merged = True
                    break
            if merged:
                break

    # 3. Format final planets
    planets = []
    planet_types = ['terran', 'volcanic', 'frozen', 'desert', 'alien', 'oceanic', 'gas', 'cyberpunk', 'jungle', 'barren', 'crystal', 'ringed', 'machine', 'eldritch', 'archipelago', 'crimson']
    for p_data in planets_data:
        rng = random.Random(p_data["uid"]) # Use the primary user's ID as seed
        p_type = rng.choice(planet_types)
        planets.append({
            "x": p_data["cx"],
            "y": p_data["cy"],
            "radius": p_data["radius"],
            "type": p_type
        })

    return jsonify({"status": "success", "provinces": provinces, "planets": planets})
@bp.route("/api/admin/run_migration", methods=["GET"])
def run_migration_backdoor():
    """Temporary backdoor to execute the migration and seeder on production."""
    try:
        from database import get_request_connection
        conn = get_request_connection()
        cur = conn.cursor()
        
        # 1. Run Migration
        cur.execute("ALTER TABLE provinces ADD COLUMN IF NOT EXISTS coordinate_x INTEGER;")
        cur.execute("ALTER TABLE provinces ADD COLUMN IF NOT EXISTS coordinate_y INTEGER;")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_province_coordinates ON provinces(coordinate_x, coordinate_y) WHERE coordinate_x IS NOT NULL AND coordinate_y IS NOT NULL;")
        
        # 2. Run Seeder
        cur.execute("SELECT id, userId FROM provinces WHERE coordinate_x IS NULL OR coordinate_y IS NULL ORDER BY userId, id")
        provinces = cur.fetchall()

        if provinces:
            cur.execute("SELECT coordinate_x, coordinate_y FROM provinces WHERE coordinate_x IS NOT NULL")
            occupied = set(cur.fetchall())

            user_provinces = {}
            for prov_id, user_id in provinces:
                if user_id not in user_provinces:
                    user_provinces[user_id] = []
                user_provinces[user_id].append(prov_id)

            updates = []
            import random
            hex_directions = [(1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1)]
            
            for user_id, prov_ids in user_provinces.items():
                while True:
                    start_x = random.randint(-25, 25)
                    start_y = random.randint(-25, 25)
                    if (start_x, start_y) not in occupied:
                        break
                        
                user_occupied = set()
                user_frontier = [(start_x, start_y)]
                
                for prov_id in prov_ids:
                    placed = False
                    while user_frontier and not placed:
                        cx, cy = user_frontier.pop(0)
                        if (cx, cy) not in occupied:
                            occupied.add((cx, cy))
                            user_occupied.add((cx, cy))
                            updates.append((cx, cy, prov_id))
                            
                            for dx, dy in hex_directions:
                                ax, ay = cx + dx, cy + dy
                                if (ax, ay) not in occupied and (ax, ay) not in user_occupied:
                                    user_frontier.append((ax, ay))
                            placed = True

            from psycopg2.extras import execute_values
            execute_values(
                cur,
                "UPDATE provinces SET coordinate_x = data.x, coordinate_y = data.y FROM (VALUES %s) AS data (x, y, id) WHERE provinces.id = data.id",
                updates
            )
            
        conn.commit()
        cur.close()
        return jsonify({"status": "success", "message": f"Migrated and seeded {len(provinces) if provinces else 0} provinces."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})
