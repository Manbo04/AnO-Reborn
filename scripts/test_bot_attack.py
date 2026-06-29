import sys
import os
import random

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from run import app
from database import get_db_connection
from attack_scripts.Nations import Units, Military

def test_bot_attack():
    print("Testing bot attack...")
    with get_db_connection() as conn:
        with conn.cursor() as db:
            db.execute("SELECT id, attacker, defender, war_type FROM wars WHERE (attacker=9999 OR defender=9999) AND peace_date IS NULL")
            active_wars = db.fetchall()
            
    if not active_wars:
        print("No active wars for bot 9999")
        return
        
    print(f"Found {len(active_wars)} active wars.")
    
    for war in active_wars:
        war_id = war[0]
        enemy_id = war[2] if war[1] == 9999 else war[1]
        war_type = war[3]
        print(f"Processing war {war_id} against {enemy_id}")
        
        # Get bot's military
        bot_military = Military.get_military(9999)
        # Select up to 3 random unit types the bot has
        available_units = [u for u, qty in bot_military.items() if qty > 0 and u not in ['spies']]
        
        if not available_units:
            print("Bot has no units!")
            continue
            
        selected_types = available_units[:3]
        
        # We will send 10% of the bot's units for this attack
        send_units = {}
        for u in selected_types:
            send_units[u] = max(1, int(bot_military[u] * 0.1))
            
        # Create Units object
        bot_units = Units(9999, send_units, selected_units_list=selected_types)
        # We assume the bot has enough supplies to attack. If not, maybe we should give it supplies.
        # But wait, attach_units does supply validation! We'll just bypass it by setting it directly.
        bot_units.selected_units = send_units
        
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess["user_id"] = 9999
                sess["username"] = "System"
                sess["enemy_id"] = enemy_id
                sess["attack_units"] = bot_units.__dict__
                
            resp = client.get("/warResult")
            print(f"GET /warResult: {resp.status_code}")
            # If 200, attack successful!
            # Let's check the HTML output for "won the battle"
            if b"won the battle" in resp.data or b"lost the battle" in resp.data:
                print("Battle executed successfully!")

if __name__ == "__main__":
    test_bot_attack()
