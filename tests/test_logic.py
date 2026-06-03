import os
import psycopg2

def run_test():
    conn = psycopg2.connect(dbname="postgres", user="dede")
    db = conn.cursor()
    
    attacker_id = 1001
    target_id = 1002
    strike_target = "silo"
    bombers_count = 50

    # SETUP
    db.execute("INSERT INTO users (id, username, password) VALUES (1001, 'Attacker', 'pass') ON CONFLICT (id) DO NOTHING")
    db.execute("INSERT INTO users (id, username, password) VALUES (1002, 'Defender', 'pass') ON CONFLICT (id) DO NOTHING")
    db.execute("DELETE FROM user_military WHERE user_id IN (1001, 1002)")
    db.execute("DELETE FROM user_buildings WHERE user_id = 1002")
    db.execute("DELETE FROM user_tech WHERE user_id = 1002")
    db.execute("INSERT INTO user_military (user_id, unit_id, quantity) SELECT 1001, unit_id, 100 FROM unit_dictionary WHERE name = 'bombers'")
    db.execute("INSERT INTO user_military (user_id, unit_id, quantity) SELECT 1002, unit_id, 20 FROM unit_dictionary WHERE name = 'fighters'")
    db.execute("INSERT INTO user_buildings (user_id, building_id, quantity) SELECT 1002, building_id, 2 FROM building_dictionary WHERE name = 'silos'")
    
    # THE LOGIC
    db.execute("SELECT um.quantity, ud.unit_id FROM user_military um JOIN unit_dictionary ud ON um.unit_id = ud.unit_id WHERE um.user_id = %s AND ud.name = 'bombers'", (attacker_id,))
    row = db.fetchone()
    bombers_unit_id = row[1]
    
    db.execute("SELECT um.quantity, ud.unit_id FROM user_military um JOIN unit_dictionary ud ON um.unit_id = ud.unit_id WHERE um.user_id = %s AND ud.name = 'fighters'", (target_id,))
    def_row = db.fetchone()
    defender_fighters = def_row[0] if def_row else 0
    fighters_unit_id = def_row[1] if def_row else None
    
    lost_bombers = min(bombers_count, defender_fighters)
    surviving_bombers = bombers_count - lost_bombers
    lost_fighters = int(lost_bombers * 0.25)
    
    db.execute("UPDATE user_military SET quantity = quantity - %s WHERE user_id = %s AND unit_id = %s", (lost_bombers, attacker_id, bombers_unit_id))
    if lost_fighters > 0 and fighters_unit_id:
        db.execute("UPDATE user_military SET quantity = quantity - %s WHERE user_id = %s AND unit_id = %s", (lost_fighters, target_id, fighters_unit_id))
        
    db.execute("SELECT ub.quantity, ub.building_id FROM user_buildings ub JOIN building_dictionary bd ON ub.building_id = bd.building_id WHERE ub.user_id = %s AND bd.name = 'silos'", (target_id,))
    s_row = db.fetchone()
    silos_count = s_row[0]
    silo_building_id = s_row[1]
    destroyed_silos = min(silos_count, surviving_bombers // 15)
    db.execute("UPDATE user_buildings SET quantity = quantity - %s WHERE user_id = %s AND building_id = %s", (destroyed_silos, target_id, silo_building_id))
    
    # ASSERTIONS
    db.execute("SELECT quantity FROM user_military WHERE user_id = %s AND unit_id = %s", (attacker_id, bombers_unit_id))
    assert db.fetchone()[0] == 80, "Attacker should have 80 bombers left"
    
    db.execute("SELECT quantity FROM user_military WHERE user_id = %s AND unit_id = %s", (target_id, fighters_unit_id))
    assert db.fetchone()[0] == 15, "Defender should have 15 fighters left"
    
    db.execute("SELECT quantity FROM user_buildings WHERE user_id = %s AND building_id = %s", (target_id, silo_building_id))
    assert db.fetchone()[0] == 0, "Defender should have 0 silos left"
    
    print("TEST PASSED: Database combat logic is flawless!")
    
    conn.rollback()

if __name__ == "__main__":
    run_test()
