import pytest
import os
import random
import psycopg2

def test_research_prereq():
    db_url = os.environ.get("DATABASE_URL", "postgresql://postgres@localhost:55450/education_t")
    
    # Run a raw check to see if we can trigger ActionLoopError for 2 universities
    from action_loop import start_research, ActionLoopError
    from database import get_db_connection
    
    with get_db_connection(db_url) as conn:
        db = conn.cursor()
        
        # Make a dummy user
        uid = 99999
        db.execute("INSERT INTO users (id, username, email, hash, date, auth_type) VALUES (%s, 'test_research', 'test_res@test', 'pw', '2026-09-28', 'local') ON CONFLICT DO NOTHING", (uid,))
        db.execute("DELETE FROM user_tech WHERE user_id=%s", (uid,))
        db.execute("DELETE FROM user_buildings WHERE user_id=%s", (uid,))
        conn.commit()
        
        db.execute("SELECT tech_id FROM tech_dictionary WHERE name = 'integrated_steelmaking'")
        row = db.fetchone()
        assert row is not None, "integrated_steelmaking tech missing"
        tech_id = row[0]
        
        # User has no universities, research should fail
        with pytest.raises(ActionLoopError, match="Universities"):
            start_research(uid, tech_id)
            
        # Add 2 universities
        db.execute("INSERT INTO provinces (id, userId, provincename) VALUES (99999, %s, 'test') ON CONFLICT DO NOTHING", (uid,))
        db.execute("DELETE FROM user_buildings WHERE user_id=%s AND building_id=(SELECT building_id FROM building_dictionary WHERE name='universities')", (uid,))
        db.execute("INSERT INTO user_buildings (user_id, province_id, building_id, quantity) VALUES (%s, 99999, (SELECT building_id FROM building_dictionary WHERE name='universities'), 2)", (uid,))
        conn.commit()
        
        # Should fail for cost now, but not for Universities!
        with pytest.raises(ActionLoopError, match="Not enough"):
            start_research(uid, tech_id)
            
        # Remove universities, but add in-progress research record
        db.execute("UPDATE user_buildings SET quantity=0 WHERE user_id=%s AND building_id=(SELECT building_id FROM building_dictionary WHERE name='universities')", (uid,))
        db.execute("INSERT INTO user_tech (user_id, tech_id, is_unlocked, research_progress) VALUES (%s, %s, FALSE, 50) ON CONFLICT (user_id, tech_id) DO UPDATE SET is_unlocked=FALSE, research_progress=50", (uid, tech_id))
        conn.commit()
        
        # User has no universities, but has in-progress tech, should bypass Universities gate and fail on cost
        with pytest.raises(ActionLoopError, match="Not enough"):
            start_research(uid, tech_id)
