from app import app
from database import get_request_cursor

def setup_users_and_military(db):
    # Create User A (Attacker) and User B (Defender)
    db.execute("INSERT INTO users (id, username, password) VALUES (1001, 'Attacker', 'pass') ON CONFLICT (id) DO NOTHING")
    db.execute("INSERT INTO users (id, username, password) VALUES (1002, 'Defender', 'pass') ON CONFLICT (id) DO NOTHING")
    
    # Initialize military
    db.execute("DELETE FROM user_military WHERE user_id IN (1001, 1002)")
    db.execute("DELETE FROM user_buildings WHERE user_id = 1002")
    db.execute("DELETE FROM user_tech WHERE user_id = 1002")
    
    # Give Attacker 100 bombers
    db.execute(
        "INSERT INTO user_military (user_id, unit_id, quantity) "
        "SELECT 1001, unit_id, 100 FROM unit_dictionary WHERE name = 'bombers'"
    )
    
    # Give Defender 20 fighters
    db.execute(
        "INSERT INTO user_military (user_id, unit_id, quantity) "
        "SELECT 1002, unit_id, 20 FROM unit_dictionary WHERE name = 'fighters'"
    )
    
    # Give Defender 2 silos
    db.execute(
        "INSERT INTO user_buildings (user_id, building_id, quantity) "
        "SELECT 1002, building_id, 2 FROM building_dictionary WHERE name = 'silos'"
    )

def test_strategic_airstrike():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    
    with get_request_cursor() as db:
        setup_users_and_military(db)
        
    client = app.test_client()
        
    with client.session_transaction() as sess:
        sess["user_id"] = 1001
        sess["username"] = "Attacker"

    # Attack Defender's Silo with 50 bombers
    response = client.post(
        "/strategic_airstrike",
        data={
            "target_id": 1002,
            "strike_target": "silo",
            "bombers_count": 50
        },
        follow_redirects=True
    )
    
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    with get_request_cursor() as db:
        # Attacker should lose 20 bombers (intercepted by 20 fighters) -> remaining 80
        db.execute(
            "SELECT quantity FROM user_military um "
            "JOIN unit_dictionary ud ON um.unit_id = ud.unit_id "
            "WHERE um.user_id = 1001 AND ud.name = 'bombers'"
        )
        bombers = db.fetchone()[0]
        assert bombers == 80, f"Expected 80 bombers, got {bombers}"

        # Defender should lose 5 fighters (25% of 20) -> remaining 15
        db.execute(
            "SELECT quantity FROM user_military um "
            "JOIN unit_dictionary ud ON um.unit_id = ud.unit_id "
            "WHERE um.user_id = 1002 AND ud.name = 'fighters'"
        )
        fighters = db.fetchone()[0]
        assert fighters == 15, f"Expected 15 fighters, got {fighters}"

        # Surviving bombers = 30. Destroyed silos = min(2, 30 // 15) = 2.
        # Defender should have 0 silos remaining.
        db.execute(
            "SELECT COALESCE(quantity, 0) FROM user_buildings ub "
            "JOIN building_dictionary bd ON ub.building_id = bd.building_id "
            "WHERE ub.user_id = 1002 AND bd.name = 'silos'"
        )
        silo_row = db.fetchone()
        silos = silo_row[0] if silo_row else 0
        assert silos == 0, f"Expected 0 silos, got {silos}"
        
        # Check news
        db.execute("SELECT description FROM news WHERE userId = 1001 ORDER BY id DESC LIMIT 1")
        news = db.fetchone()[0]
        assert "destroyed 2 Missile Silo(s)" in news, f"Expected news to mention 2 silos, got {news}"
        
    print("ALL TESTS PASSED: Strategic Airstrike works perfectly!")

if __name__ == "__main__":
    test_strategic_airstrike()
