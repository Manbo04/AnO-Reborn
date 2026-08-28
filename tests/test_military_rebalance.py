import pytest
from database import get_db_cursor
from attack_scripts.Nations import Military
from app_core.military.services import compute_display_limits, get_unit_costs
from app_core.military.repositories import get_building_counts
from variables import MILDICT

def test_rebalanced_unit_costs():
    """Verify that the naval and special units have the new rebalanced, weight-scaled costs in both the DB and variables.py."""
    with get_db_cursor() as db:
        # Check Destroyers
        db.execute("SELECT production_cost_steel, production_cost_components, production_cost_fuel, production_cost_rations FROM unit_dictionary WHERE name = 'destroyers'")
        row = db.fetchone()
        assert row is not None
        assert row[0] == 120000
        assert row[1] == 15000
        assert row[2] == 4000
        assert row[3] == 0
        
        # Check Nukes -- migration 0043 moved this unit's steel cost to aluminium;
        # migration 0051 added a uranium requirement
        db.execute("SELECT production_cost_steel, production_cost_components, production_cost_fuel, production_cost_rations, production_cost_aluminium, production_cost_uranium FROM unit_dictionary WHERE name = 'nukes'")
        row = db.fetchone()
        assert row is not None
        assert row[0] == 0
        assert row[1] == 100000
        assert row[2] == 25000
        assert row[3] == 0
        assert row[4] == 120000
        assert row[5] == 20000

        # Check Spies
        db.execute("SELECT production_cost_steel, production_cost_components, production_cost_fuel, production_cost_rations FROM unit_dictionary WHERE name = 'spies'")
        row = db.fetchone()
        assert row is not None
        assert row[0] == 0
        assert row[1] == 2000
        assert row[2] == 0
        assert row[3] == 100

    # Verify variables.py matches
    assert MILDICT["destroyers"]["resources"] == {"steel": 120000, "components": 15000, "gasoline": 4000}
    assert MILDICT["nukes"]["resources"] == {"aluminium": 120000, "components": 100000, "gasoline": 25000, "uranium": 20000}
    assert MILDICT["spies"]["resources"] == {"rations": 100, "components": 2000}

def test_aerodrome_spelling_mismatch_fallback():
    """Verify that get_building_counts handles both 'aerodromes' and 'aerodomes' properly."""
    with get_db_cursor() as db:
        # Get building ID for aerodromes/aerodomes
        db.execute("SELECT building_id, name FROM building_dictionary WHERE name IN ('aerodromes', 'aerodomes')")
        rows = db.fetchall()
        assert len(rows) > 0
        building_id = rows[0][0]
        original_name = rows[0][1]

        # Insert a dummy user and a building for that user
        TEST_UID = 16
        
        # Temporarily rename building to 'aerodomes' (production spelling)
        db.execute("UPDATE building_dictionary SET name = 'aerodomes' WHERE building_id = %s", (building_id,))
        
        db.execute("SELECT quantity FROM user_buildings WHERE user_id = %s AND building_id = %s", (TEST_UID, building_id))
        existing = db.fetchone()
        orig_qty = existing[0] if existing else None

        if orig_qty is not None:
            db.execute("UPDATE user_buildings SET quantity = 3 WHERE user_id = %s AND building_id = %s", (TEST_UID, building_id))
        else:
            db.execute("INSERT INTO user_buildings (user_id, building_id, quantity) VALUES (%s, %s, 3)", (TEST_UID, building_id))
        
        # Fetch counts
        counts = get_building_counts(db, TEST_UID)
        # index 2 corresponds to aerodromes/aerodomes
        assert counts[2] >= 3

        # Cleanup and restore
        if orig_qty is not None:
            db.execute("UPDATE user_buildings SET quantity = %s WHERE user_id = %s AND building_id = %s", (orig_qty, TEST_UID, building_id))
        else:
            db.execute("DELETE FROM user_buildings WHERE user_id = %s AND building_id = %s", (TEST_UID, building_id))
        db.execute("UPDATE building_dictionary SET name = %s WHERE building_id = %s", (original_name, building_id))
        db.connection.commit()

def test_fighter_helicopter_combat_balance():
    """Verify that FighterUnit gets a bonus against apaches, and ApacheUnit gets no bonus against fighters or bombers."""
    from units import FighterUnit, ApacheUnit
    
    # Fighter vs Apache
    fighter = FighterUnit(5)
    fighter_effects = fighter.attack("apaches")
    assert fighter_effects[0] == 500
    assert fighter_effects[1] == 15  # +3 bonus per unit -> 15

    # Apache vs Fighter and Bomber (should be 0 bonus)
    apache = ApacheUnit(5)
    apache_vs_fighter = apache.attack("fighters")
    assert apache_vs_fighter[1] == 0
    
    apache_vs_bomber = apache.attack("bombers")
    assert apache_vs_bomber[1] == 0

    # Apache vs Land (should still have bonus)
    apache_vs_tank = apache.attack("tanks")
    assert apache_vs_tank[1] == 5
