import os
import json
from flask import Blueprint, request, jsonify, current_app
from database import get_db_connection
from helpers import login_required

events_bp = Blueprint('events_bp', __name__)

def load_events():
    events_path = os.path.join(os.path.dirname(__file__), 'events.json')
    if os.path.exists(events_path):
        with open(events_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return {item.get('id'): item for item in data if 'id' in item}
            return data
    return {}

@events_bp.route("/api/events/<int:event_id>/respond", methods=["POST"])
@login_required
def respond_event(cId, event_id):
    data = request.get_json()
    if not data or 'option_index' not in data:
        return jsonify({"success": False, "message": "Missing option_index"}), 400
        
    option_index = int(data['option_index'])
    events_data = load_events()
    
    with get_db_connection() as conn:
        db = conn.cursor()
        
        # Check event
        db.execute("SELECT user_id, event_def_id, resolved_at FROM interactive_events WHERE id = %s", (event_id,))
        event = db.fetchone()
        
        if not event:
            return jsonify({"success": False, "message": "Event not found"}), 404
            
        user_id, event_def_id, resolved_at = event
        
        if user_id != cId:
            return jsonify({"success": False, "message": "Unauthorized"}), 403
            
        if resolved_at is not None:
            return jsonify({"success": False, "message": "Event already resolved"}), 400
            
        event_def = events_data.get(event_def_id)
        if not event_def:
            return jsonify({"success": False, "message": "Event definition not found"}), 500
            
        options = event_def.get("options", [])
        if option_index < 0 or option_index >= len(options):
            return jsonify({"success": False, "message": "Invalid option"}), 400
            
        option = options[option_index]
        costs = option.get("costs", {})
        rewards = option.get("rewards", {})
        
        # Load resource dictionary to map names to ids
        db.execute("SELECT name, resource_id FROM resource_dictionary")
        resource_map = {row[0]: row[1] for row in db.fetchall()}
        
        # Check if user has enough resources for costs
        for cost_resource_name, cost_amount in costs.items():
            res_id = resource_map.get(cost_resource_name)
            if not res_id:
                return jsonify({"success": False, "message": f"Unknown resource {cost_resource_name}"}), 500
                
            db.execute("SELECT quantity FROM user_economy WHERE user_id = %s AND resource_id = %s", (cId, res_id))
            row = db.fetchone()
            current_qty = row[0] if row else 0
            
            if current_qty < cost_amount:
                return jsonify({"success": False, "message": f"Not enough {cost_resource_name}"}), 400
                
        # Deduct costs
        for cost_resource_name, cost_amount in costs.items():
            res_id = resource_map.get(cost_resource_name)
            db.execute("UPDATE user_economy SET quantity = quantity - %s WHERE user_id = %s AND resource_id = %s", (cost_amount, cId, res_id))
            
        # Apply rewards
        for reward_resource_name, reward_amount in rewards.items():
            res_id = resource_map.get(reward_resource_name)
            db.execute("""
                INSERT INTO user_economy (user_id, resource_id, quantity) 
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id, resource_id) 
                DO UPDATE SET quantity = user_economy.quantity + %s
            """, (cId, res_id, reward_amount, reward_amount))
            
        # Mark as resolved
        db.execute("UPDATE interactive_events SET resolved_at = now(), chosen_option_index = %s WHERE id = %s", (option_index, event_id))
        
        conn.commit()
        
    return jsonify({"success": True, "message": "Event resolved successfully"})
