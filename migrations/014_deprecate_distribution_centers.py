"""
Deprecate distribution_centers so they don't appear in the Quick Build menu.
"""

def up(db):
    print("Deprecating distribution_centers...")
    db.execute("UPDATE building_dictionary SET is_active = FALSE WHERE name = 'distribution_centers'")
    
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
