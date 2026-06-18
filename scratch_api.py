from flask import jsonify
from database import get_request_cursor

# Add to province.py
@bp.route("/api/global_events", methods=["GET"])
def get_global_events():
    events = []
    try:
        with get_request_cursor() as db:
            # 1. Newest nation
            db.execute("SELECT username FROM users ORDER BY id DESC LIMIT 1")
            res = db.fetchone()
            if res:
                events.append(f"A new nation, {res[0]}, has risen to power in Terra.")
            
            # 2. Newest province
            db.execute("SELECT name FROM provinces ORDER BY id DESC LIMIT 1")
            res = db.fetchone()
            if res:
                events.append(f"New territory established: the province of {res[0]} has been settled.")
                
            # 3. Market shortages (resources with 0 quantity)
            db.execute("""
                SELECT rd.name 
                FROM resource_dictionary rd
                LEFT JOIN global_market gm ON rd.resource_id = gm.resource_id
                WHERE gm.quantity IS NULL OR gm.quantity = 0
                LIMIT 3
            """)
            shortages = db.fetchall()
            for row in shortages:
                events.append(f"Global market crisis: {row[0]} supplies have been completely exhausted!")
                
            # 4. Recent treaties/alliances (if coalitions exist)
            db.execute("SELECT name FROM coalitions_normalized ORDER BY id DESC LIMIT 1")
            res = db.fetchone()
            if res:
                events.append(f"Diplomatic breakthrough: The {res[0]} coalition gathers strength.")
                
            # 5. Battles/Wars
            db.execute("SELECT attacker_name, defender_name FROM wars_normalized ORDER BY id DESC LIMIT 1")
            res = db.fetchone()
            if res:
                events.append(f"Conflict erupts! {res[0]} has declared war on {res[1]}.")
    except Exception as e:
        print("Error fetching global events:", e)
        pass
        
    return jsonify({"events": events})
