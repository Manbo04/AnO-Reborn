import os
import json
from flask import Blueprint, request, jsonify, current_app
from database import get_db_connection
from helpers import login_required

events_bp = Blueprint('events_bp', __name__)

_cached_events = None

def load_events():
    global _cached_events
    if _cached_events is not None:
        return _cached_events
        
    events_path = os.path.join(os.path.dirname(__file__), 'events.json')
    if os.path.exists(events_path):
        with open(events_path, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                _cached_events = {item.get('id'): item for item in data if 'id' in item}
            else:
                _cached_events = data
            return _cached_events
    _cached_events = {}
    return _cached_events

@events_bp.route("/api/events/<int:event_id>/respond", methods=["POST"])
@login_required
def respond_event(event_id):
    from flask import session
    cId = session.get("user_id")
    data = request.get_json()
    if not data or 'option_index' not in data:
        return jsonify({"success": False, "message": "Missing option_index"}), 400

    option_index = int(data['option_index'])
    events_data = load_events()

    with get_db_connection() as conn:
        db = conn.cursor()

        # Serializes this user's event responses (same pattern as
        # buildings/military/loans/spy elsewhere). Found 2026-09-13: the
        # cost deduction below is a blind `quantity = quantity - %s` (no
        # WHERE-guard), and the final "mark as resolved" UPDATE has no
        # `AND resolved_at IS NULL` condition either -- two concurrent
        # responses to the same event could both pass the `resolved_at is
        # None` check, both deduct costs, and both grant rewards, netting a
        # duplicate reward for a single cost payment.
        db.execute("SELECT pg_advisory_xact_lock(%s)", (cId,))

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
        db.execute("SELECT gold FROM stats WHERE id = %s", (cId,))
        gold_row = db.fetchone()
        gold_now = int(gold_row[0] or 0) if gold_row else 0

        def _held(name):
            db.execute("SELECT quantity FROM user_economy WHERE user_id = %s AND resource_id = %s",
                       (cId, resource_map[name]))
            r = db.fetchone()
            return int(r[0] or 0) if r else 0

        def _resolve(spec, is_cost):
            """Turn {"gold_pct": 3, "rations": 800} into [(name, amount, label)] with
            absolute amounts. *_pct keys are a percentage of what the player holds now,
            so events matter for both 80M newcomers and billion-gold veterans."""
            out = []
            for key, val in (spec or {}).items():
                pct = key.endswith("_pct")
                name = key[:-4] if pct else key
                if name != "gold" and name not in resource_map:
                    raise ValueError(f"Unknown resource {name}")
                held = gold_now if name == "gold" else _held(name)
                if pct:
                    amount = held * int(val) // 100
                    if amount <= 0:
                        amount = 0 if is_cost else (1 if name == "gold" else 50)
                else:
                    amount = int(val)
                if amount <= 0:
                    continue
                sign = "-" if is_cost else "+"
                label = name.replace("_", " ")
                text = f"{sign}{val}% {label} ({sign}{amount:,})" if pct else f"{sign}{amount:,} {label}"
                out.append((name, amount, text, held))
            return out

        try:
            cost_list = _resolve(costs, True)
            reward_list = _resolve(rewards, False)
        except ValueError as exc:
            return jsonify({"success": False, "message": str(exc)}), 500
        for name, amount, _, held in cost_list:
            if held < amount:
                return jsonify({"success": False, "message": f"Not enough {name.replace('_', ' ')}"}), 400
        for name, amount, _, _ in cost_list:
            if name == "gold":
                db.execute("UPDATE stats SET gold = gold - %s WHERE id = %s AND gold >= %s RETURNING gold",
                           (amount, cId, amount))
            else:
                db.execute("UPDATE user_economy SET quantity = quantity - %s WHERE user_id = %s "
                           "AND resource_id = %s AND quantity >= %s RETURNING quantity",
                           (amount, cId, resource_map[name], amount))
            if db.fetchone() is None:
                conn.rollback()
                return jsonify({"success": False, "message": f"Not enough {name.replace('_', ' ')}"}), 400
        for name, amount, _, _ in reward_list:
            if name == "gold":
                db.execute("UPDATE stats SET gold = gold + %s WHERE id = %s", (amount, cId))
            else:
                db.execute("""
                    INSERT INTO user_economy (user_id, resource_id, quantity)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, resource_id)
                    DO UPDATE SET quantity = user_economy.quantity + %s
                """, (cId, resource_map[name], amount, amount))
        summary = [t for _, _, t, _ in cost_list + reward_list]

        db.execute("UPDATE interactive_events SET resolved_at = now(), chosen_option_index = %s WHERE id = %s", (option_index, event_id))
        
        conn.commit()
        
    return jsonify({"success": True, "message": "Event resolved successfully", "summary": summary})
