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

@bp.route("/api/world_map/nodes/<int:node_id>/attack", methods=["POST"])
@login_required
def declare_siege(node_id):
    """Declare an attack on a node. Costs Intel."""
    user_id = session.get("user_id")
    with get_request_cursor() as db:
        # Check user's coalition
        db.execute(
            """
            SELECT c.id, c.name
            FROM colNames c
            JOIN coalitions_legacy m ON c.id = m.colid
            WHERE m.userid = %s
            """, (user_id,)
        )
        user_col = db.fetchone()
        if not user_col:
            return jsonify({"status": "error", "message": "You must be in a Coalition to attack nodes."})
            
        coalition_id, coalition_name = user_col
        
        # Lock user row to prevent concurrent money spending
        db.execute("SELECT gold FROM stats WHERE id = %s FOR UPDATE", (user_id,))
        money = db.fetchone()[0]
        
        if money < 5000000:
            return jsonify({"status": "error", "message": "You need $5,000,000 to fund a siege deployment."})
            
        # Lock node row to prevent concurrent captures overriding shields
        db.execute("SELECT name, controlling_coalition_id, shield_expires_at FROM nodes WHERE id = %s FOR UPDATE", (node_id,))
        node = db.fetchone()
        if not node:
            return jsonify({"status": "error", "message": "Node not found."})
            
        node_name, controlling_id, shield_expires_at = node
        
        if controlling_id == coalition_id:
            return jsonify({"status": "error", "message": "Your coalition already controls this node!"})
            
        if shield_expires_at:
            from datetime import datetime, timezone
            if shield_expires_at > datetime.now(timezone.utc):
                return jsonify({"status": "error", "message": "This node is currently protected by a shield."})
        
        # Deduct money and set the node ownership instantly
        db.execute("UPDATE stats SET gold = gold - 5000000 WHERE id = %s", (user_id,))
        db.execute(
            "UPDATE nodes SET controlling_coalition_id = %s, shield_expires_at = CURRENT_TIMESTAMP + INTERVAL '12 hours' WHERE id = %s",
            (coalition_id, node_id)
        )
        
        return jsonify({"status": "success", "message": f"Successfully captured {node_name} for {coalition_name}!"})
