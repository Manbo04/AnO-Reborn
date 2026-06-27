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
    """Render the HTML/CSS infinite canvas story map."""
    return render_template("lore_map.html")
