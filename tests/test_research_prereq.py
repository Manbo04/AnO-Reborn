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
        db.execute("INSERT INTO users (id, name, email, password) VALUES (%s, 'test_research', 'test_res@test', 'pw') ON CONFLICT DO NOTHING", (uid,))
        db.execute("INSERT INTO user_economy (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (uid,))
        conn.commit()
        
        db.execute("SELECT tech_id FROM tech_dictionary WHERE name = 'integrated_steelmaking'")
        row = db.fetchone()
        assert row is not None, "integrated_steelmaking tech missing"
        tech_id = row[0]
        
        # User has no universities, research should fail
        with pytest.raises(ActionLoopError, match="Universities"):
            start_research(uid, tech_id)
            
        # Add 2 universities
        db.execute("INSERT INTO user_buildings (user_id, building_id, quantity) VALUES (%s, (SELECT building_id FROM building_dictionary WHERE name='universities'), 2) ON CONFLICT (user_id, building_id) DO UPDATE SET quantity=2", (uid,))
        conn.commit()
        
        # Should fail for cost now, but not for Universities!
        with pytest.raises(ActionLoopError, match="does not have enough"):
            start_research(uid, tech_id)
