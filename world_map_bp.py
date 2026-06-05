from flask import Blueprint, request, render_template, session, jsonify
from helpers import login_required
from database import get_request_cursor

bp = Blueprint("world_map", __name__)

@bp.route("/world_map")
@login_required
def world_map_view():
    """Render the PixiJS Interactive World Map."""
    # We will need some basic user context, like their coalition ID, to highlight their nodes.
    with get_request_cursor(read_only=True) as db:
        user_id = session.get("user_id")
        # Fetch user's coalition ID if they are in one
        db.execute(
            """
            SELECT c.id, c.name 
            FROM colNames c
            JOIN coalitions_legacy m ON c.id = m.colid
            WHERE m.userid = %s
            """, (user_id,)
        )
        user_col = db.fetchone()
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
    with get_request_cursor(read_only=True) as db:
        db.execute(
            """
            SELECT 
                n.id, n.name, n.type, n.coordinate_x, n.coordinate_y, 
                n.controlling_coalition_id, c.name as coalition_name,
                n.health, n.shield_expires_at
            FROM nodes n
            LEFT JOIN colNames c ON n.controlling_coalition_id = c.id
            """
        )
        nodes = db.fetchall()
        
        # Build the JSON response
        node_list = []
        for n in nodes:
            node_list.append({
                "id": n[0],
                "name": n[1],
                "type": n[2],
                "x": n[3],
                "y": n[4],
                "controlling_coalition_id": n[5],
                "coalition_name": n[6],
                "health": n[7],
                "shield_expires_at": n[8].isoformat() if n[8] else None,
            })
            
    return jsonify({"status": "success", "nodes": node_list})
