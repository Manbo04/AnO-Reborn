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

@bp.route("/api/world_map/nodes/<int:node_id>/attack", methods=["POST"])
@login_required
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
            SELECT p.id, p.name, p.user_id, u.username, p.coordinate_x, p.coordinate_y,
                   p.population, p.tax_rate, p.unrest, p.corruption
            FROM provinces p
            JOIN users u ON p.user_id = u.id
            WHERE p.coordinate_x IS NOT NULL AND p.coordinate_y IS NOT NULL
        """)
        rows = db.fetchall()
        
    provinces = []
    for r in rows:
        provinces.append({
            "id": r[0],
            "name": r[1],
            "user_id": r[2],
            "username": r[3],
            "x": r[4],
            "y": r[5],
            "population": r[6],
            "tax_rate": r[7],
            "unrest": r[8],
            "corruption": r[9]
        })
        
    return jsonify({"status": "success", "provinces": provinces})
