"""
Fix base_cost in building_dictionary for economy rebalance buildings.
They were accidentally given their MONEY cost instead of their STEEL cost.
"""

def up(db):
    fixes = {
        "hydro_dams": 120000,
        "gas_stations": 60000,
        "farmers_markets": 110000,
        "city_parks": 22000,
        "monorails": 600000,
        "admin_buildings": 135000,
        "silos": 1080000,
        "lead_mines": 45000,
        "distribution_centers": 45000
    }
    
    print("Fixing building base costs (steel) for dictionary buildings...")
    for name, cost in fixes.items():
        db.execute("UPDATE building_dictionary SET base_cost = %s WHERE name = %s", (cost, name))
        print(f"Updated {name} to {cost} steel.")
    
    # Optional: Clear redis cache for active buildings
    try:
        from database import redis_client
        if redis_client:
            redis_client.delete("cache:building_dictionary_active")
            print("Cleared Redis cache for building_dictionary_active")
    except Exception as e:
        print(f"Could not clear cache: {e}")

def down(db):
    pass
