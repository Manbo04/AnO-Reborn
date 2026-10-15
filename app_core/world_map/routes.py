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

    # Keep each nation's provinces on its own world. The old overlap merge
    # repeatedly compared every planet pair and folded nearby nations together,
    # which was both expensive and visually misleading as the map grew.
    user_clusters = {}
    for province in provinces:
        user_clusters.setdefault(province["user_id"], []).append(province)

    import math
    import random

    planet_types = [
        "terran", "volcanic", "frozen", "desert", "alien", "oceanic",
        "gas", "cyberpunk", "jungle", "barren", "crystal", "ringed",
        "machine", "eldritch", "archipelago", "crimson",
    ]
    def world_slots():
        # Lay worlds out in a deterministic hex spiral. Province coordinates are
        # translated with their world so a player's local province layout stays
        # intact while separate nations keep enough space between their planets.
        yield (0, 0)
        directions = [(1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1)]
        ring = 1
        while True:
            q, r = 0, -ring
            for dq, dr in directions:
                for _ in range(ring):
                    yield (q, r)
                    q += dq
                    r += dr
            ring += 1

    viewer_id = session.get("user_id")
    planets = []
    slots = world_slots()
    world_spacing = 48
    for user_id in sorted(user_clusters, key=lambda value: (value is None, value or 0)):
        cluster_provinces = user_clusters[user_id]
        center_x = sum(province["x"] for province in cluster_provinces) / len(cluster_provinces)
        center_y = sum(province["y"] for province in cluster_provinces) / len(cluster_provinces)
        extent = max(
            (math.hypot(province["x"] - center_x, province["y"] - center_y)
             for province in cluster_provinces),
            default=0,
        )
        # Radius is in rendered map pixels. Leave room around the outermost
        # province so clusters read as complete planets instead of tiny badges.
        radius = min(1350, max(360, extent * 120 + 360))
        slot_q, slot_r = next(slots)
        world_x = slot_q * world_spacing
        world_y = slot_r * world_spacing
        offset_x = world_x - center_x
        offset_y = world_y - center_y
        for province in cluster_provinces:
            province["x"] += offset_x
            province["y"] += offset_y

        owner_name = next(
            (province["username"] for province in cluster_provinces if province["username"]),
            "Unknown nation",
        )
        rng = random.Random(user_id)
        planets.append({
            "x": world_x,
            "y": world_y,
            "radius": radius,
            "type": rng.choice(planet_types),
            "name": owner_name,
            "is_home": user_id == viewer_id,
            "province_count": len(cluster_provinces),
        })

    planets.sort(key=lambda planet: (not planet["is_home"], planet["name"].casefold()))
    return jsonify({"status": "success", "provinces": provinces, "planets": planets})

@bp.route("/api/admin/run_migration", methods=["GET"])
@login_required
def run_migration_backdoor():
    """Temporary backdoor to execute the migration and seeder on production.

    Was completely unauthenticated (no login_required, no admin check) --
    any anonymous internet request could trigger it, re-running ALTER
    TABLE/index creation and re-seeding coordinate_x/coordinate_y for
    every province still missing them. Gated behind the same super-admin
    allowlist as the rest of the admin toolkit rather than removed
    outright, since new provinces without coordinates may still depend on
    this being re-run occasionally.
    """
    from app_core.admin.services import admin_only_guard

    denied = admin_only_guard(session.get("user_id"))
    if denied:
        return denied
    try:
        from database import get_request_connection
        conn = get_request_connection()
        cur = conn.cursor()
        
        # Seed coordinates (columns + index come from migration 0037)
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
